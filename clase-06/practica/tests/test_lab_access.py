"""Compose contract for exploring the lab from pgAdmin and from inside the containers."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
REDIS_SCRIPT = (ROOT / "examples" / "03-redis.sh").read_text(encoding="utf-8")
PGADMIN_STORAGE = "/var/lib/pgadmin/storage/student_example.edu"


def _service(name: str) -> str:
    block = COMPOSE.split(f"\n  {name}:\n", 1)[1]
    return block.split("\n\n", 1)[0]


def _env_example() -> dict[str, str]:
    return {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in ENV_EXAMPLE.splitlines()
        if "=" in line and not line.startswith("#")
    }


def test_pgadmin_is_local_configurable_and_waits_for_postgres() -> None:
    block = _service("pgadmin")

    assert "image: dpage/pgadmin4:" in block
    assert '"127.0.0.1:${PGADMIN_PORT:-5056}:80"' in block
    assert "PGADMIN_DEFAULT_EMAIL: ${PGADMIN_DEFAULT_EMAIL:-student@example.edu}" in block
    assert "PGADMIN_DEFAULT_PASSWORD: ${PGADMIN_DEFAULT_PASSWORD:-class6-local}" in block
    assert "pgadmin_data:/var/lib/pgadmin" in block
    assert "condition: service_healthy" in block
    assert "\n  pgadmin_data:" in COMPOSE.split("\nvolumes:\n", 1)[1]


def test_pgadmin_file_dialog_exposes_sql_scripts_read_only() -> None:
    block = _service("pgadmin")

    # Mounting inside pgAdmin's storage dir leaves it root-owned and pgAdmin refuses to boot.
    assert PGADMIN_STORAGE not in block
    assert "./postgres/examples:/lab/examples:ro" in block
    assert "./postgres/seed:/lab/seed:ro" in block
    assert "PGADMIN_CONFIG_SHARED_STORAGE:" in block
    assert '"path": "/lab/examples", "restricted_access": True' in block
    assert '"path": "/lab/seed", "restricted_access": True' in block


def test_sql_and_redis_scripts_are_mounted_inside_their_containers() -> None:
    postgres = _service("postgres")
    redis = _service("redis")

    assert "./postgres/examples:/lab/examples:ro" in postgres
    assert "./postgres/seed:/lab/seed:ro" in postgres
    assert "./examples:/lab/examples:ro" in redis


def test_seaweedfs_web_uis_are_published_on_localhost_only() -> None:
    block = _service("seaweedfs")

    assert '"127.0.0.1:${SEAWEEDFS_S3_PORT:-18333}:8333"' in block
    assert '"127.0.0.1:${SEAWEEDFS_FILER_PORT:-18888}:8888"' in block
    assert '"127.0.0.1:${SEAWEEDFS_MASTER_PORT:-19333}:9333"' in block


def test_env_example_documents_the_new_access_variables() -> None:
    values = _env_example()

    assert values.get("PGADMIN_PORT") == "5056"
    assert values.get("PGADMIN_DEFAULT_EMAIL") == "student@example.edu"
    assert values.get("PGADMIN_DEFAULT_PASSWORD") == "class6-local"
    assert values.get("SEAWEEDFS_FILER_PORT") == "18888"
    assert values.get("SEAWEEDFS_MASTER_PORT") == "19333"


def test_redis_example_runs_from_the_host_or_inside_the_redis_container() -> None:
    assert "command -v docker" in REDIS_SCRIPT
    assert 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw "$@"' in REDIS_SCRIPT
    assert "compose exec -T redis" in REDIS_SCRIPT


def test_redisinsight_connects_to_redis_and_is_local_only() -> None:
    block = _service("redisinsight")

    assert "image: redis/redisinsight:" in block
    assert '"127.0.0.1:${REDISINSIGHT_PORT:-5540}:5540"' in block
    assert "RI_REDIS_HOST: redis" in block
    assert 'RI_REDIS_PORT: "6379"' in block
    assert "RI_REDIS_PASSWORD: ${REDIS_PASSWORD:-ceiot_redis_local_only}" in block
    assert "redisinsight_data:/data" in block
    assert "condition: service_healthy" in block
    assert "\n  redisinsight_data:" in COMPOSE.split("\nvolumes:\n", 1)[1]
    assert _env_example().get("REDISINSIGHT_PORT") == "5540"
