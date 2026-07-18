"""PostgreSQL run-log connection wrapper.

Reads connection settings from the OTS environment (via :data:`daqpy.env.env`)::

    OTSDAQ_RUNINFO_DATABASE        — database name
    OTSDAQ_RUNINFO_DATABASE_HOST   — server hostname
    OTSDAQ_RUNINFO_DATABASE_PORT   — server port (default 5432)
    OTSDAQ_RUNINFO_DATABASE_USER   — username
    OTSDAQ_RUNINFO_DATABASE_PWD    — password
    OTSDAQ_RUNINFO_DATABASE_SCHEMA — search_path schema (e.g. ``test_sc``)

Schema overview (relevant tables/views)::

    view_run_summary   — primary read surface: run + end_info + config joined
    run                — one row per run (run_number, run_type, create_time, comment)
    run_end_info       — stop time and end comment
    run_transition     — state-machine transitions with timestamps
    subrun             — per-subrun event counts (n_events, n_on_spill, …)
    config             — per-subsystem JSONB configuration snapshot

Typical usage::

    from daqpy.runlog import RunLog

    rl = RunLog()
    print(rl.get_run(1234))
    print(rl.get_run_totals(1234))

    with rl.connect() as conn:
        rows = conn.execute("SELECT * FROM view_run_summary LIMIT 5").fetchall()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

log = logging.getLogger(__name__)


def _require_psycopg():
    try:
        import psycopg  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "psycopg is required for runlog support. "
            "Install it with:  pip install 'daqpy[runlog]'"
        ) from e


class RunLog:
    """Interface to the OTS run-info PostgreSQL database.

    Connection parameters are read from the environment via
    :class:`daqpy.env.RunInfoDB`.  You can also supply an explicit
    :class:`daqpy.env.RunInfoDB` instance for testing.

    Args:
        db_env: Override the environment-derived connection config.
    """

    def __init__(self, db_env=None):
        _require_psycopg()
        if db_env is None:
            from daqpy.env import env
            db_env = env.db.runinfo
        self._cfg = db_env
        self._conn = None
        self._validate()

    def _validate(self):
        missing = [
            var for var, val in [
                ("OTSDAQ_RUNINFO_DATABASE_HOST", self._cfg.host),
                ("OTSDAQ_RUNINFO_DATABASE",      self._cfg.name),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Run-log database not configured. Missing env vars: {', '.join(missing)}"
            )

    def _connect_kwargs(self) -> dict[str, Any]:
        cfg = self._cfg
        kw: dict[str, Any] = {
            "host":   cfg.host,
            "dbname": cfg.name,
        }
        if cfg.port:
            kw["port"] = cfg.port
        if cfg.user:
            kw["user"] = cfg.user
        if cfg.password:
            kw["password"] = cfg.password
        if cfg.schema:
            kw["options"] = f"-c search_path={cfg.schema}"
        return kw

    @contextmanager
    def connect(self) -> Generator:
        """Context manager yielding an open :class:`psycopg.Connection`.

        Reuses a persistent connection; reconnects automatically if the
        connection has been closed or lost.

        Use this for raw queries or transactions::

            with rl.connect() as conn:
                rows = conn.execute("SELECT * FROM view_run_summary LIMIT 5").fetchall()
        """
        import psycopg

        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(**self._connect_kwargs())
        try:
            yield self._conn
        except Exception:
            # On any error close so next call gets a fresh connection
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetchall_as_dicts(self, sql: str, params=()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            cols = [desc.name for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _fetchone_as_dict(self, sql: str, params=()) -> dict[str, Any] | None:
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            cols = [desc.name for desc in cur.description]
            return dict(zip(cols, row))

    # ------------------------------------------------------------------
    # Run summary (view_run_summary)
    # Columns: run_number, comment, run_status, run_type_name,
    #          start_time, stop_time, end_comment,
    #          subsystems_list, host_name, artdaq_partition, config_alias
    # ------------------------------------------------------------------

    def get_run(self, run_number: int) -> dict[str, Any] | None:
        """Return a summary row for a single run, or ``None`` if not found.

        Queries ``view_run_summary`` which already joins ``run``,
        ``run_end_info``, and config metadata.
        """
        return self._fetchone_as_dict(
            "SELECT * FROM view_run_summary WHERE run_number = %s",
            (run_number,),
        )

    def get_recent_runs(self, n: int = 10) -> list[dict[str, Any]]:
        """Return the ``n`` most recent runs, newest first.

        Avoids querying ``view_run_summary`` directly (which aggregates the
        entire config/transition tables before LIMIT applies).  Instead picks
        the top-N run numbers first, then resolves each row with scoped
        lookups so indexes on run_number are used.
        """
        return self._fetchall_as_dicts(
            """
            WITH top_runs AS (
                SELECT run_number, comment, run_type_id
                FROM run
                ORDER BY run_number DESC
                LIMIT %s
            )
            SELECT
                r.run_number,
                r.comment,
                CASE lt.type_id
                    WHEN 0 THEN 'halt'
                    WHEN 1 THEN 'completed'
                    WHEN 2 THEN 'error'
                    WHEN 3 THEN 'pause'
                    WHEN 4 THEN 'resume'
                    WHEN 5 THEN 'start'
                    ELSE 'unknown'
                END AS run_status,
                rt.name       AS run_type_name,
                ts.transition_time AS start_time,
                te.transition_time AS stop_time,
                rei.comment   AS end_comment,
                sub.subsystems_list,
                gw.host_name,
                gw.artdaq_partition,
                gw.config_alias
            FROM top_runs r
            LEFT JOIN run_type rt ON rt.id = r.run_type_id
            LEFT JOIN LATERAL (
                SELECT type_id FROM run_transition
                WHERE run_number = r.run_number
                ORDER BY transition_time DESC LIMIT 1
            ) lt ON true
            LEFT JOIN LATERAL (
                SELECT transition_time FROM run_transition
                WHERE run_number = r.run_number AND type_id = 5
                LIMIT 1
            ) ts ON true
            LEFT JOIN LATERAL (
                SELECT transition_time FROM run_transition
                WHERE run_number = r.run_number AND type_id = 1
                LIMIT 1
            ) te ON true
            LEFT JOIN run_end_info rei ON rei.run_number = r.run_number
            LEFT JOIN LATERAL (
                SELECT string_agg((subsystem || ': ') ||
                    COALESCE(((config -> 'config') -> 'groups') ->> 'Configuration_alias', 'N/A'),
                    ', ') AS subsystems_list
                FROM config WHERE run_number = r.run_number
            ) sub ON true
            LEFT JOIN LATERAL (
                SELECT
                    string_agg((config -> 'env') ->> 'HOSTNAME', ', ')        AS host_name,
                    string_agg((config -> 'env') ->> 'ARTDAQ_PARTITION', ', ') AS artdaq_partition,
                    string_agg(config ->> 'config_alias', ', ')               AS config_alias
                FROM config
                WHERE run_number = r.run_number AND subsystem = 'Gateway'
            ) gw ON true
            ORDER BY r.run_number DESC
            """,
            (n,),
        )

    def get_run_types(self) -> list[str]:
        """Return all run type names from the ``run_type`` lookup table, sorted."""
        rows = self._fetchall_as_dicts(
            "SELECT name FROM run_type WHERE name IS NOT NULL ORDER BY name", []
        )
        return [r["name"] for r in rows]

    def find_runs(
        self,
        run_type: str | None = None,
        run_status: str | None = None,
        subsystem: str | None = None,
        run_from: int | None = None,
        run_to: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search ``view_run_summary`` with optional filters, newest first.

        Args:
            run_type:   Filter by ``run_type_name`` (exact match).
            run_status: Filter by ``run_status`` (exact match).
            subsystem:  Filter by ``subsystems_list`` containing this name.
            run_from:   Only include runs >= this number.
            run_to:     Only include runs <= this number.
            limit:      Maximum rows to return.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if run_type:
            clauses.append("rt.name = %s")
            params.append(run_type)
        if run_status:
            clauses.append("""CASE lt.type_id
                    WHEN 0 THEN 'halt' WHEN 1 THEN 'completed' WHEN 2 THEN 'error'
                    WHEN 3 THEN 'pause' WHEN 4 THEN 'resume' WHEN 5 THEN 'start'
                    ELSE 'unknown' END = %s""")
            params.append(run_status)
        if subsystem:
            clauses.append("sub.subsystems_list ILIKE %s")
            params.append(f"%{subsystem}%")
        if run_from is not None:
            clauses.append("r.run_number >= %s")
            params.append(run_from)
        if run_to is not None:
            clauses.append("r.run_number <= %s")
            params.append(run_to)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        return self._fetchall_as_dicts(
            f"""
            SELECT
                r.run_number,
                r.comment,
                CASE lt.type_id
                    WHEN 0 THEN 'halt' WHEN 1 THEN 'completed' WHEN 2 THEN 'error'
                    WHEN 3 THEN 'pause' WHEN 4 THEN 'resume'   WHEN 5 THEN 'start'
                    ELSE 'unknown'
                END AS run_status,
                rt.name       AS run_type_name,
                ts.transition_time AS start_time,
                te.transition_time AS stop_time,
                rei.comment   AS end_comment,
                sub.subsystems_list,
                gw.host_name,
                gw.artdaq_partition,
                gw.config_alias
            FROM run r
            LEFT JOIN run_type rt ON rt.id = r.run_type_id
            LEFT JOIN LATERAL (
                SELECT type_id FROM run_transition
                WHERE run_number = r.run_number
                ORDER BY transition_time DESC LIMIT 1
            ) lt ON true
            LEFT JOIN LATERAL (
                SELECT transition_time FROM run_transition
                WHERE run_number = r.run_number AND type_id = 5 LIMIT 1
            ) ts ON true
            LEFT JOIN LATERAL (
                SELECT transition_time FROM run_transition
                WHERE run_number = r.run_number AND type_id = 1 LIMIT 1
            ) te ON true
            LEFT JOIN run_end_info rei ON rei.run_number = r.run_number
            LEFT JOIN LATERAL (
                SELECT string_agg((subsystem || ': ') ||
                    COALESCE(((config -> 'config') -> 'groups') ->> 'Configuration_alias', 'N/A'),
                    ', ') AS subsystems_list
                FROM config WHERE run_number = r.run_number
            ) sub ON true
            LEFT JOIN LATERAL (
                SELECT
                    string_agg((config -> 'env') ->> 'HOSTNAME', ', ')        AS host_name,
                    string_agg((config -> 'env') ->> 'ARTDAQ_PARTITION', ', ') AS artdaq_partition,
                    string_agg(config ->> 'config_alias', ', ')               AS config_alias
                FROM config
                WHERE run_number = r.run_number AND subsystem = 'Gateway'
            ) gw ON true
            {where}
            ORDER BY r.run_number DESC
            LIMIT %s
            """,
            params,
        )

    # ------------------------------------------------------------------
    # Subrun / event counts
    # Columns: run, subrun, n_events, n_on_spill, n_off_spill,
    #          n_null, min_ewt, max_ewt, start_time_unix, stop_time_unix,
    #          event_mode_counts (jsonb), created_at
    # ------------------------------------------------------------------

    def get_run_subruns(self, run_number: int) -> list[dict[str, Any]]:
        """Return all subrun rows for a run, ordered by subrun number."""
        return self._fetchall_as_dicts(
            "SELECT * FROM subrun WHERE run = %s ORDER BY subrun",
            (run_number,),
        )

    def get_run_totals(self, run_number: int) -> dict[str, Any]:
        """Return aggregated event counts across all subruns for a run.

        Returns a dict with keys:
            ``run``, ``n_subruns``, ``n_events``, ``n_on_spill``,
            ``n_off_spill``, ``n_null``, ``start_time_unix``, ``stop_time_unix``.
        Returns ``None`` values for all counts if no subrun data exists yet.
        """
        row = self._fetchone_as_dict(
            """
            SELECT
                run,
                COUNT(*)           AS n_subruns,
                SUM(n_events)      AS n_events,
                SUM(n_on_spill)    AS n_on_spill,
                SUM(n_off_spill)   AS n_off_spill,
                SUM(n_null)        AS n_null,
                MIN(start_time_unix) AS start_time_unix,
                MAX(stop_time_unix)  AS stop_time_unix
            FROM subrun
            WHERE run = %s
            GROUP BY run
            """,
            (run_number,),
        )
        if row is None:
            return {
                "run": run_number,
                "n_subruns": 0,
                "n_events": None,
                "n_on_spill": None,
                "n_off_spill": None,
                "n_null": None,
                "start_time_unix": None,
                "stop_time_unix": None,
            }
        return row

    # ------------------------------------------------------------------
    # Transitions
    # run_transition columns: run_number, type_id, cause_id, transition_time
    # joined with run_transition_type (id, name) and run_transition_cause (id, name)
    # ------------------------------------------------------------------

    def get_run_transitions(self, run_number: int) -> list[dict[str, Any]]:
        """Return state transitions for a run with resolved type and cause names."""
        return self._fetchall_as_dicts(
            """
            SELECT
                rt.transition_time,
                rtt.name  AS transition_type,
                rtc.name  AS transition_cause
            FROM run_transition rt
            JOIN run_transition_type rtt ON rtt.id = rt.type_id
            LEFT JOIN run_transition_cause rtc ON rtc.id = rt.cause_id
            WHERE rt.run_number = %s
            ORDER BY rt.transition_time
            """,
            (run_number,),
        )

    # ------------------------------------------------------------------
    # Config
    # config columns: run_number, subsystem, config (jsonb), create_time
    # ------------------------------------------------------------------

    def get_run_config(
        self, run_number: int, subsystem: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the per-subsystem config snapshot(s) for a run.

        Args:
            run_number: The run number.
            subsystem:  If given, return only the matching subsystem row.
        """
        if subsystem:
            return self._fetchall_as_dicts(
                "SELECT * FROM config WHERE run_number = %s AND subsystem = %s",
                (run_number, subsystem),
            )
        return self._fetchall_as_dicts(
            "SELECT * FROM config WHERE run_number = %s ORDER BY subsystem",
            (run_number,),
        )

    # ------------------------------------------------------------------
    # Config views
    # view_run_subsystems columns: run_number, run_type, subsystem, configuration_alias
    # view_run_config columns:     run_number, run_type, subsystems (text[]), alias,
    #                              group_name, group_key  (all jsonb)
    # view_config_trigger columns: run_number, create_time, config, name, version (jsonb)
    # ------------------------------------------------------------------

    def get_run_subsystems(self, run_number: int) -> list[dict[str, Any]]:
        """Return one row per subsystem that participated in a run.

        Queries ``view_run_subsystems`` (columns: run_number, run_type,
        subsystem, configuration_alias).
        """
        return self._fetchall_as_dicts(
            "SELECT * FROM view_run_subsystems WHERE run_number = %s ORDER BY subsystem",
            (run_number,),
        )

    def get_run_config_summary(self, run_number: int) -> dict[str, Any] | None:
        """Return the high-level config metadata for a run.

        Queries ``view_run_config`` (columns: run_number, run_type, subsystems,
        alias, group_name, group_key).  Returns ``None`` if not found.
        """
        return self._fetchone_as_dict(
            "SELECT * FROM view_run_config WHERE run_number = %s",
            (run_number,),
        )

    def get_run_config_trigger(self, run_number: int) -> dict[str, Any] | None:
        """Return the trigger-subsystem config details for a run.

        Queries ``view_config_trigger`` (columns: run_number, create_time,
        config, name, version).  Returns ``None`` if not found.
        """
        return self._fetchone_as_dict(
            "SELECT * FROM view_config_trigger WHERE run_number = %s",
            (run_number,),
        )

    # ------------------------------------------------------------------
    # Arbitrary query escape hatch
    # ------------------------------------------------------------------

    def query(self, sql: str, params=()) -> list[dict[str, Any]]:
        """Execute an arbitrary SELECT and return rows as plain dicts.

        Args:
            sql:    Parameterized SQL query (use ``%s`` placeholders).
            params: Sequence of bind values.
        """
        return self._fetchall_as_dicts(sql, params)

    # ------------------------------------------------------------------
    # Performance indexes
    # ------------------------------------------------------------------

    # These indexes target the expensive parts of view_run_summary:
    #   1. DISTINCT ON (run_number) ORDER BY run_number, transition_time DESC
    #   2. JOIN ... WHERE type_id IN (1, 5)  (start/stop transitions)
    #   3. config GROUP BY run_number         (subsystems_list aggregation)
    #   4. config WHERE subsystem = 'Gateway' (gateway subquery)
    _INDEXES: list[tuple[str, str]] = [
        (
            "idx_run_transition_run_time",
            "CREATE INDEX IF NOT EXISTS idx_run_transition_run_time "
            "ON run_transition (run_number, transition_time DESC)",
        ),
        (
            "idx_run_transition_run_type",
            "CREATE INDEX IF NOT EXISTS idx_run_transition_run_type "
            "ON run_transition (run_number, type_id)",
        ),
        (
            "idx_config_run_number",
            "CREATE INDEX IF NOT EXISTS idx_config_run_number "
            "ON config (run_number)",
        ),
        (
            "idx_config_subsystem_run",
            "CREATE INDEX IF NOT EXISTS idx_config_subsystem_run "
            "ON config (subsystem, run_number)",
        ),
    ]

    def create_indexes(self, verbose: bool = True) -> list[str]:
        """Create performance indexes for ``view_run_summary`` if they don't exist.

        Safe to run multiple times — all statements use ``IF NOT EXISTS``.
        Returns list of index names that were processed.
        """
        created = []
        with self.connect() as conn:
            for name, ddl in self._INDEXES:
                if verbose:
                    log.info("Applying index: %s", name)
                conn.execute(ddl)
                created.append(name)
            conn.commit()
        return created

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        cfg = self._cfg
        port = f":{cfg.port}" if cfg.port else ""
        schema = f"/{cfg.schema}" if cfg.schema else ""
        return (
            f"RunLog(host={cfg.host!r}, db={cfg.name!r}{port}{schema}, "
            f"user={cfg.user!r})"
        )
