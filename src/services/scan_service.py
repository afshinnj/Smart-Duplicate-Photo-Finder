"""Scan pipeline orchestration.

Implements the multi-stage pipeline from the specification:

```
files -> image detection -> metadata -> SHA256 -> exact duplicates
     -> perceptual hash -> similarity -> feature matching -> AI -> groups
```

Every stage is independent and can be enabled or disabled through the
configuration. CPU-bound work is spread across a thread pool, the UI receives
progress ticks for each stage, and the whole run can be paused, resumed or
cancelled at any point.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..ai.ai_engine import AIEngine, create_ai_engine
from ..core import system_info
from ..core.config import AppConfig
from ..core.constants import ScanStatus
from ..core.exceptions import ScanCancelled
from ..core.logger import get_logger
from ..database.database import Database
from ..database.repositories.image_repository import ImageRepository
from ..database.repositories.scan_repository import GroupRepository, ScanRepository
from ..hashing.file_hash import FileHashEngine
from ..hashing.hash_cache import HashCache
from ..hashing.perceptual_hash import HASH_BITS, PerceptualHashEngine
from ..models.duplicate_group import DuplicateGroup
from ..models.image_model import ImageRecord
from ..models.scan_session import ScanSession
from ..models.similarity_result import SimilarityResult
from ..scanner.drive_scanner import DriveScanner
from ..scanner.file_scanner import FileScanner, ScanContext
from ..scanner.image_detector import ImageDetector
from ..similarity.similarity_engine import SimilarityEngine
from .duplicate_service import DuplicateService
from .progress import ProgressCallback, ProgressUpdate, ScanStage

_log = get_logger("scan.service")

# Width (in bits) of the perceptual-hash prefix used to bucket candidates.
# 10 bits -> 1024 buckets, which keeps candidate generation near-linear while
# still catching resized / re-compressed / re-encoded copies.
_BUCKET_BITS = 10
_BUCKET_MASK = (1 << _BUCKET_BITS) - 1
# Locality-sensitive bucketing: a pair becomes a candidate when its perceptual
# hashes agree on *any* 16-bit block of *any* hash family. This catches crops
# and recoloured copies that shift the high bits of every single hash.
_BLOCK_BITS = 16
_BLOCK_OFFSETS = (0, 16, 32, 48)
_BLOCK_COUNT = 1 << _BLOCK_BITS
# Maximum Hamming distance for a pair to become a similarity candidate.
_CANDIDATE_HAMMING = max(12, int(0.35 * HASH_BITS))
_HASH_BATCH_SIZE = 128
# Blended perceptual score below which a candidate pair is dropped before the
# expensive (image-loading) similarity stages ever run.
_PERCEPTUAL_FLOOR = 40.0

# Relative weight of each stage in the overall progress bar.
_STAGE_WEIGHTS = {
    ScanStage.SCANNING: 0.25,
    ScanStage.METADATA: 0.35,
    ScanStage.PERCEPTUAL: 0.15,
    ScanStage.SIMILARITY: 0.20,
    ScanStage.GROUPING: 0.05,
}


@dataclass
class ScanResult:
    """Everything produced by a completed scan."""

    session: ScanSession
    groups: List[DuplicateGroup] = field(default_factory=list)
    image_count: int = 0
    duplicate_count: int = 0
    recoverable_bytes: int = 0
    skipped_files: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def status(self) -> ScanStatus:
        return self.session.status


class ScanController:
    """Pause / resume / cancel handle for a running scan."""

    def __init__(self) -> None:
        self.context = ScanContext()

    def pause(self) -> None:
        self.context.request_pause()

    def resume(self) -> None:
        self.context.request_resume()

    def cancel(self) -> None:
        self.context.request_cancel()

    @property
    def is_cancelled(self) -> bool:
        return self.context.cancel_requested

    @property
    def is_paused(self) -> bool:
        return self.context.pause_requested


class ScanService:
    """Runs the full duplicate detection pipeline against a database."""

    def __init__(
        self,
        database: Database,
        config: Optional[AppConfig] = None,
        ai_engine: Optional[AIEngine] = None,
    ) -> None:
        self.database = database
        self.config = config or AppConfig()
        self.ai_engine = ai_engine
        self.image_repository = ImageRepository(database)
        self.scan_repository = ScanRepository(database)
        self.group_repository = GroupRepository(database)
        self.hash_engine = FileHashEngine()
        self.perceptual_engine = PerceptualHashEngine()
        self.similarity_engine = SimilarityEngine(self.config.similarity)
        self.duplicate_service = DuplicateService(self.config)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def scan_folders(
        self,
        folders: Sequence[str],
        progress: Optional[ProgressCallback] = None,
        controller: Optional[ScanController] = None,
    ) -> ScanResult:
        """Scan the given folders and return the duplicate groups found."""
        return self._run(list(folders), progress, controller)

    def scan_drives(
        self,
        include_removable: bool = True,
        progress: Optional[ProgressCallback] = None,
        controller: Optional[ScanController] = None,
    ) -> ScanResult:
        """Scan every mounted drive (or only fixed drives)."""
        scanner = DriveScanner(self.config.scan)
        return self._run(scanner.drive_roots(include_removable=include_removable), progress, controller)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _run(
        self,
        roots: List[str],
        progress: Optional[ProgressCallback],
        controller: Optional[ScanController],
    ) -> ScanResult:
        controller = controller or ScanController()
        session = ScanSession(folders=roots, start_time=_now(), status=ScanStatus.RUNNING)
        session.id = self.scan_repository.create(session)

        started = time.time()
        result = ScanResult(session=session)
        stage_progress = _StageProgress(_STAGE_WEIGHTS)

        try:
            if self.ai_engine is None:
                self.ai_engine = create_ai_engine(self.config.ai)

            # ---- Stage 1: filesystem walk ---------------------------------
            self._emit(progress, stage_progress, ScanStage.SCANNING, controller, session)
            scanned_files, image_files = self._scan_filesystem(
                roots, controller, progress, stage_progress, session
            )
            result.session.files_scanned = scanned_files

            # ---- Stage 2: metadata + hashing ------------------------------
            self._emit(progress, stage_progress, ScanStage.METADATA, controller, session)
            records = self._compute_metadata_and_hashes(
                image_files, controller, progress, stage_progress, session
            )
            result.image_count = len(records)
            result.session.images_found = result.image_count

            # ---- Stage 3: exact duplicates --------------------------------
            self._emit(progress, stage_progress, ScanStage.EXACT_DUPLICATES, controller, session)
            exact_groups = self.duplicate_service.group_exact(records, scan_id=session.id)
            stage_progress.complete(ScanStage.EXACT_DUPLICATES)

            # ---- Stage 4 + 5: perceptual candidates + pairwise scoring ----
            self._emit(progress, stage_progress, ScanStage.PERCEPTUAL, controller, session)
            candidates = self._find_candidates(records, progress, stage_progress, session)
            stage_progress.complete(ScanStage.PERCEPTUAL)

            self._emit(progress, stage_progress, ScanStage.SIMILARITY, controller, session)
            results = self._compare_candidates(
                records, candidates, controller, progress, stage_progress, session
            )
            stage_progress.complete(ScanStage.SIMILARITY)

            # ---- Stage 6: grouping ----------------------------------------
            self._emit(progress, stage_progress, ScanStage.GROUPING, controller, session)
            similar_groups = self.duplicate_service.group_similar(
                records, results, scan_id=session.id
            )

            groups = self._merge_groups(exact_groups, similar_groups, session.id or 0)
            self.group_repository.store_groups(groups, self.image_repository)
            stage_progress.complete(ScanStage.GROUPING)

            result.groups = groups
            result.duplicate_count = self.duplicate_service.duplicate_count(groups)
            result.recoverable_bytes = self.duplicate_service.recoverable_space(groups)
            processing_errors = []
            processing_error_count = 0
            for record in records:
                if record.error:
                    processing_error_count += 1
                    if len(processing_errors) < 100:
                        processing_errors.append(f"{record.path}: {record.error}")
            all_errors = [*controller.context.errors, *processing_errors]
            result.skipped_files = controller.context.error_count + processing_error_count
            result.errors = all_errors[:200]

            # ---- Finalise ---------------------------------------------------
            self._emit(progress, stage_progress, ScanStage.FINALIZING, controller, session)
            session.duplicates_found = result.duplicate_count
            session.space_recoverable = result.recoverable_bytes
            session.end_time = _now()
            session.status = ScanStatus.COMPLETED
            self.scan_repository.finish(
                session.id or 0,
                ScanStatus.COMPLETED,
                session.files_scanned,
                session.images_found,
                session.duplicates_found,
                session.space_recoverable,
            )
            stage_progress.complete(ScanStage.FINALIZING)
            stage_progress.complete(ScanStage.DONE)
            self._emit(progress, stage_progress, ScanStage.DONE, controller, session, result=result)

            _log.info(
                "Scan %s finished: %d files, %d images, %d groups, %d duplicates in %.1fs",
                session.id,
                session.files_scanned,
                result.image_count,
                len(groups),
                result.duplicate_count,
                time.time() - started,
            )
            return result

        except ScanCancelled:
            session.status = ScanStatus.CANCELLED
            session.end_time = _now()
            self.scan_repository.finish(
                session.id or 0,
                ScanStatus.CANCELLED,
                session.files_scanned,
                session.images_found,
                session.duplicates_found,
                session.space_recoverable,
                "cancelled by user",
            )
            self._emit(progress, stage_progress, ScanStage.CANCELLED, controller, session)
            result.groups = []
            return result
        except Exception as exc:
            _log.exception("Scan failed")
            session.status = ScanStatus.FAILED
            session.error = str(exc)
            session.end_time = _now()
            self.scan_repository.finish(
                session.id or 0,
                ScanStatus.FAILED,
                session.files_scanned,
                session.images_found,
                0,
                0,
                str(exc),
            )
            self._emit(progress, stage_progress, ScanStage.FAILED, controller, session, error=str(exc))
            raise

    # ------------------------------------------------------------------
    # Stage 1: filesystem walk
    # ------------------------------------------------------------------

    def _scan_filesystem(
        self,
        roots: List[str],
        controller: ScanController,
        progress: Optional[ProgressCallback],
        stage_progress: _StageProgress,
        session: ScanSession,
    ) -> Tuple[int, List]:
        scanner = FileScanner(self.config.scan)
        detector = ImageDetector(self.config.scan.image_extensions)
        image_files = []
        last_tick = time.time()

        for scanned_file in scanner.scan(roots, controller.context):
            image_files.append(scanned_file)
            if time.time() - last_tick > 0.1:
                self._emit(
                    progress,
                    stage_progress,
                    ScanStage.SCANNING,
                    controller,
                    session,
                    files_scanned=controller.context.files_scanned,
                    images_found=controller.context.images_found,
                    current_path=scanned_file.path,
                    stage_progress_value=100.0
                    * stage_progress.fraction(
                        ScanStage.SCANNING, len(image_files), len(image_files) + 500
                    ),
                    rate=controller.context.files_per_second,
                    eta_seconds=self._scan_eta(controller, len(image_files)),
                )
                last_tick = time.time()

        self._emit(
            progress,
            stage_progress,
            ScanStage.SCANNING,
            controller,
            session,
            files_scanned=controller.context.files_scanned,
            images_found=controller.context.images_found,
            stage_progress_value=100.0,
        )
        stage_progress.complete(ScanStage.SCANNING)
        _log.info(
            "Walked %d files, found %d images, recorded %d scan issues",
            controller.context.files_scanned,
            len(image_files),
            controller.context.error_count,
        )
        return controller.context.files_scanned, image_files

    def _scan_eta(self, controller: ScanController, found: int) -> float:
        rate = controller.context.files_per_second
        if rate <= 0:
            return 0.0
        # Rough projection: the walk is roughly uniform in time per directory entry.
        scanned = max(1, controller.context.files_scanned)
        projected = scanned * 1.05
        return max(0.0, (projected - scanned) / rate)

    # ------------------------------------------------------------------
    # Stage 2: metadata + hashing (threaded)
    # ------------------------------------------------------------------

    def _compute_metadata_and_hashes(
        self,
        image_files: Sequence,
        controller: ScanController,
        progress: Optional[ProgressCallback],
        stage_progress: _StageProgress,
        session: ScanSession,
    ) -> List[ImageRecord]:
        cache = HashCache(self.database)
        detector = ImageDetector(self.config.scan.image_extensions)
        workers = self._worker_count()
        records: List[ImageRecord] = []
        processed = 0
        last_tick = time.time()

        def process_file(scanned) -> ImageRecord:
            cached = cache.lookup(scanned.path, scanned.size, scanned.modified_at)
            if cached is not None:
                cached.scan_id = session.id
                return cached
            return self._hash_fresh(scanned, detector, session.id)

        failures = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for offset in range(0, len(image_files), _HASH_BATCH_SIZE):
                if controller.is_cancelled:
                    raise ScanCancelled()
                batch = image_files[offset : offset + _HASH_BATCH_SIZE]
                futures = {pool.submit(process_file, scanned): scanned for scanned in batch}
                for future in as_completed(futures):
                    if controller.is_cancelled:
                        for pending in futures:
                            pending.cancel()
                        raise ScanCancelled()
                    try:
                        record = future.result()
                    except Exception as exc:
                        failures += 1
                        scanned = futures[future]
                        controller.context.add_error(
                            f"{scanned.path}: {type(exc).__name__}: {exc}"
                        )
                        _log.debug("Hashing failed: %s", exc)
                        continue
                    if record is None:
                        failures += 1
                        controller.context.add_error(
                            f"{futures[future].path}: could not be processed"
                        )
                        continue
                    records.append(record)
                    processed += 1
                    if time.time() - last_tick > 0.15:
                        self._emit(
                            progress,
                            stage_progress,
                            ScanStage.METADATA,
                            controller,
                            session,
                            images_found=processed,
                            current_path=record.path,
                            stage_progress_value=100.0 * processed / max(1, len(image_files)),
                        )
                        last_tick = time.time()

        # Persist everything now so every record carries a database id, which
        # the grouping stage needs to link duplicate groups back to images.
        fresh = [record for record in records if record.id is None]
        cached = [record for record in records if record.id is not None]
        self.image_repository.insert_and_assign_ids(fresh)
        self.image_repository.update_scan_ids(cached)

        if failures:
            _log.warning("Metadata stage skipped %d files that could not be processed", failures)

        self._emit(
            progress,
            stage_progress,
            ScanStage.METADATA,
            controller,
            session,
            images_found=len(records),
            stage_progress_value=100.0,
        )
        stage_progress.complete(ScanStage.METADATA)
        return records

    def _hash_fresh(self, scanned, detector, scan_id: Optional[int]) -> Optional[ImageRecord]:
        """Compute metadata, SHA-256 and perceptual hashes for one file."""
        record = detector.build_records([scanned], scan_id=scan_id)[0]

        metadata = detector.read_metadata(scanned.path)
        if metadata is None:
            record.error = detector.detect_error(scanned.path) or "unreadable"
            return record
        record.width, record.height = metadata.width, metadata.height

        try:
            record.sha256 = self.hash_engine.hash_file(scanned.path)
        except Exception as exc:  # hashing must never abort the scan
            _log.debug("SHA-256 failed for %s: %s", scanned.path, exc)

        try:
            hashes = self.perceptual_engine.compute_all(scanned.path)
            record.ahash, record.dhash = hashes["ahash"], hashes["dhash"]
            record.phash, record.whash = hashes["phash"], hashes["whash"]
        except Exception as exc:
            _log.debug("Perceptual hashing failed for %s: %s", scanned.path, exc)

        return record

    # ------------------------------------------------------------------
    # Stage 4: candidate generation via perceptual-hash buckets
    # ------------------------------------------------------------------

    def _find_candidates(
        self,
        records: Sequence[ImageRecord],
        progress: Optional[ProgressCallback],
        stage_progress: _StageProgress,
        session: ScanSession,
    ) -> List[Tuple[int, int, float]]:
        """Locality-sensitive bucketing of perceptual hashes.

        A pair becomes a candidate when its perceptual hashes agree on any
        16-bit block of any hash family (pHash / aHash / dHash). Blocks are
        spread across the full 64 bits, so a crop that shifts the high bits of
        every hash is still caught by a block in the middle. Only pairs whose
        Hamming distance on the triggering family is small enough survive, which
        keeps the expensive pairwise stage near-linear on large collections.
        """
        hash_families = (
            ("phash", ImageRecord.phash_int),
            ("ahash", ImageRecord.ahash_int),
            ("dhash", ImageRecord.dhash_int),
        )

        seen_pairs: set[tuple] = set()
        candidates: List[Tuple[int, int, float]] = []
        processed = 0

        # Pre-extract the hash values once so bucketing never re-reads them.
        values: Dict[str, List[Optional[int]]] = {}
        for hash_name, getter in hash_families:
            values[hash_name] = [getter(record) for record in records]

        total_blocks = len(hash_families) * len(_BLOCK_OFFSETS)
        processed = 0
        for hash_name, _ in hash_families:
            family_values = values[hash_name]
            for offset in _BLOCK_OFFSETS:
                buckets: Dict[int, List[int]] = {}
                for index, value in enumerate(family_values):
                    if value is None:
                        continue
                    buckets.setdefault((value >> offset) & (_BLOCK_COUNT - 1), []).append(index)

                for bucket in buckets.values():
                    if len(bucket) < 2:
                        continue
                    for i in range(len(bucket)):
                        for j in range(i + 1, len(bucket)):
                            index_a, index_b = bucket[i], bucket[j]
                            key = (index_a, index_b) if index_a < index_b else (index_b, index_a)
                            if key in seen_pairs:
                                continue
                            # A pair may share blocks in several hash families.
                            # Record it before scoring so rejected pairs are not
                            # recomputed for every matching block.
                            seen_pairs.add(key)
                            score = self._hash_similarity(
                                hash_name, records[index_a], records[index_b]
                            )
                            if score is not None and score >= 55.0:
                                id_a = int(records[index_a].id or -1)
                                id_b = int(records[index_b].id or -1)
                                candidates.append((id_a, id_b, score))
                processed += 1
                if progress is not None:
                    self._emit(
                        progress,
                        stage_progress,
                        ScanStage.PERCEPTUAL,
                        None,
                        session,
                        stage_progress_value=100.0 * processed / total_blocks,
                        message=f"{len(candidates)} candidate pairs",
                    )

        _log.info("Perceptual stage produced %d candidate pairs", len(candidates))
        return candidates

    @staticmethod
    def _hash_similarity(hash_name: str, record_a: ImageRecord, record_b: ImageRecord) -> Optional[float]:
        from ..hashing.perceptual_hash import similarity_percentage

        return similarity_percentage(getattr(record_a, hash_name), getattr(record_b, hash_name))

    # ------------------------------------------------------------------
    # Stage 5: pairwise comparison
    # ------------------------------------------------------------------

    def _compare_candidates(
        self,
        records: Sequence[ImageRecord],
        candidates: Sequence[Tuple[int, int, float]],
        controller: ScanController,
        progress: Optional[ProgressCallback],
        stage_progress: _StageProgress,
        session: ScanSession,
    ) -> List[SimilarityResult]:
        by_id = {record.id: record for record in records if record.id is not None}
        results: List[SimilarityResult] = []
        processed = 0
        last_tick = time.time()

        for image_a_id, image_b_id, phash_score in candidates:
            if controller.is_cancelled:
                raise ScanCancelled()
            record_a = by_id.get(image_a_id)
            record_b = by_id.get(image_b_id)
            if record_a is None or record_b is None:
                continue

            # Cheap pre-filter: when the blended perceptual score is very low,
            # no combination of the expensive stages can reach the grouping
            # threshold, so skip the image loading entirely.
            blended = self.similarity_engine.perceptual_score(record_a, record_b)
            if blended is not None and blended < _PERCEPTUAL_FLOOR:
                continue

            try:
                result = self.similarity_engine.compare(record_a, record_b)
            except Exception as exc:
                _log.debug("Comparison failed for %s / %s: %s", record_a.path, record_b.path, exc)
                continue

            if result.score >= self.config.similarity.similar_threshold - 10.0:
                results.append(result)

            processed += 1
            if time.time() - last_tick > 0.2:
                self._emit(
                    progress,
                    stage_progress,
                    ScanStage.SIMILARITY,
                    controller,
                    session,
                    stage_progress_value=100.0 * processed / max(1, len(candidates)),
                    message=f"{len(results)} similar pairs",
                )
                last_tick = time.time()

        return results

    # ------------------------------------------------------------------
    # Group merging
    # ------------------------------------------------------------------

    def _merge_groups(
        self,
        exact_groups: List[DuplicateGroup],
        similar_groups: List[DuplicateGroup],
        scan_id: int,
    ) -> List[DuplicateGroup]:
        """Keep exact groups and add similar groups that are not already covered."""
        seen: Dict[frozenset, DuplicateGroup] = {}

        for group in exact_groups:
            seen[frozenset(item.id for item in group.items)] = group

        for group in similar_groups:
            key = frozenset(item.id for item in group.items)
            if key in seen:
                continue
            # Skip similar groups that are fully contained in an exact group.
            if any(key <= other_key for other_key in seen if len(other_key) > 1):
                continue
            seen[key] = group

        groups = list(seen.values())
        groups.sort(key=lambda group: (not group.is_exact, -group.similarity_score))
        return groups

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _worker_count(self) -> int:
        configured = self.config.scan.max_workers
        if configured and configured > 0:
            return min(configured, 32)
        return max(2, min(16, system_info.cpu_count() * 2))

    def _emit(
        self,
        progress: Optional[ProgressCallback],
        stage_tracker: "_StageProgress",
        stage: ScanStage,
        controller: Optional[ScanController],
        session: ScanSession,
        files_scanned: int = 0,
        images_found: int = 0,
        current_path: str = "",
        stage_progress_value: float = 0.0,
        rate: float = 0.0,
        eta_seconds: float = 0.0,
        message: str = "",
        error: Optional[str] = None,
        result: Optional[ScanResult] = None,
    ) -> None:
        if progress is None:
            return
        context = controller.context if controller else None
        progress(
            ProgressUpdate(
                stage=stage,
                files_scanned=files_scanned or (context.files_scanned if context else 0),
                images_found=images_found or (context.images_found if context else 0),
                current_path=current_path,
                stage_progress=stage_progress_value,
                overall_progress=100.0 * stage_tracker.overall(),
                elapsed_seconds=time.time() - session.start_time.timestamp()
                if session.start_time
                else 0.0,
                rate=rate,
                eta_seconds=eta_seconds,
                message=message,
                error=error,
                groups_found=len(result.groups) if result else 0,
                duplicates_found=result.duplicate_count if result else 0,
                space_recoverable=result.recoverable_bytes if result else 0,
            )
        )


def _now():
    from datetime import datetime

    return datetime.now()


class _StageProgress:
    """Accumulates per-stage completion into an overall 0-1 fraction."""

    def __init__(self, weights: Dict[ScanStage, float]) -> None:
        self.weights = {stage: weight for stage, weight in weights.items() if weight > 0}
        self.completed: Dict[ScanStage, float] = {}

    def fraction(self, stage: ScanStage, items: int = 0, total: int = 1) -> float:
        if stage in self.completed:
            return self.completed[stage]
        if stage not in self.weights:
            return 0.0
        return self.weights[stage] * (items / max(1, total))

    def complete(self, stage: ScanStage) -> None:
        if stage in self.weights:
            self.completed[stage] = self.weights[stage]

    def overall(self) -> float:
        total = sum(self.weights.values())
        if total <= 0:
            return 0.0
        return min(1.0, sum(self.completed.values()) / total)
