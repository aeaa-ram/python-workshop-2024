"""Gatekeeper: near-duplicates blocked, unrelated tools pass."""

import pytest

from examples.make_fixtures import make_beam_notebook, make_crack_width_xlsx
from src.ingestion import DuplicateToolError, grind
from src.ingestion.base import get_parser
from src.knowledge_graph import build_index, check_request, check_submission


@pytest.fixture
def seeded_repo(tmp_path):
    repo = tmp_path / "repo"
    xlsx = make_crack_width_xlsx(tmp_path)
    grind(xlsx, repo, skip_gatekeeper=True)
    return repo, xlsx


def test_regrinding_same_file_is_blocked(seeded_repo):
    repo, xlsx = seeded_repo
    with pytest.raises(DuplicateToolError):
        grind(xlsx, repo)


def test_force_overrides_gatekeeper(seeded_repo):
    repo, xlsx = seeded_repo
    result = grind(xlsx, repo, force=True)
    assert any(m.verdict == "duplicate" for m in result.gatekeeper_report)


def test_unrelated_tool_passes(seeded_repo, tmp_path):
    repo, _ = seeded_repo
    nb = make_beam_notebook(tmp_path)
    parsed = get_parser(nb).parse(nb)
    assert check_submission(parsed, repo) == []
    grind(nb, repo)  # must not raise


def test_hypothetical_request_warns(seeded_repo):
    repo, _ = seeded_repo
    matches = check_request(
        "Crack width verification for RC slab to EN 1992-1-1",
        description="crack width check for reinforced concrete slab",
        variables=["w_k", "s_r_max", "phi", "A_s", "w_max"],
        repo_dir=repo,
    )
    assert matches, "expected the gatekeeper to flag the similar request"
    assert matches[0].verdict in ("duplicate", "similar")


def test_index_and_relationships(seeded_repo, tmp_path):
    repo, _ = seeded_repo
    nb = make_beam_notebook(tmp_path)
    grind(nb, repo, skip_gatekeeper=True)
    index = build_index(repo)
    assert len(index["tools"]) == 2
    assert (repo / ".index.json").exists()
