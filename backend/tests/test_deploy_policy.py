from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKED_PATHS = [
    ROOT / "DEPLOY.md",
    ROOT / "SPEC.md",
    ROOT / "scripts",
    ROOT / ".github",
]


def _repo_text_files():
    for base in CHECKED_PATHS:
        if not base.exists():
            continue
        if base.is_file():
            yield base
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {"", ".md", ".sh", ".yml", ".yaml"}:
                yield path


def _has_min_zero(text: str) -> bool:
    return "--min-instances=0" in text or "--min-instances 0" in text or "min-instances=0" in text


def _has_gamma_max_one(text: str) -> bool:
    return "--max-instances=1" in text or "--max-instances 1" in text or "max-instances=1" in text


def test_cloud_run_policy_is_documented():
    deploy = (ROOT / "DEPLOY.md").read_text()
    spec = (ROOT / "SPEC.md").read_text()

    assert "min-instances=0" in deploy
    assert "Gamma Cloud Run services" in deploy
    assert "max-instances=1" in deploy
    assert "min-instances=0" in spec
    assert "max-instances=1" in spec


def test_cloud_run_deploy_commands_pin_instance_policy():
    offenders: list[str] = []
    for path in _repo_text_files():
        text = path.read_text(errors="ignore")
        if "gcloud run" not in text:
            continue

        relative = path.relative_to(ROOT)
        if "min-instances=1" in text or "--min-instances=1" in text or "--min-instances 1" in text:
            offenders.append(f"{relative}: must not set Cloud Run min instances above 0")

        if "gcloud run deploy" in text or "gcloud run services update" in text:
            if not _has_min_zero(text):
                offenders.append(f"{relative}: Cloud Run commands must pin min-instances=0")
            if "gamma" in text.lower() and not _has_gamma_max_one(text):
                offenders.append(f"{relative}: gamma Cloud Run commands must pin max-instances=1")

    assert offenders == []
