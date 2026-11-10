"""The viewer as a page without its server (``flow.web.artifactifier``)."""

from __future__ import annotations


def test_an_artifacts_answer_files_are_named_by_their_query() -> None:
    """The artifactifier names each server answer's file as the page's ``apiUrl`` asks for it in a
    snapshot: the query, its characters outside [A-Za-z0-9._-] as ``_``, its type's extension."""
    from flow.web.artifactifier import api_name

    assert (
        api_name("wave", {"path": "build/samp/x/result.h5", "record": 0})
        == "api/wave/path_build_2Fsamp_2Fx_2Fresult.h5_record_0.json"
    )
    assert api_name("log", {"path": "build/a b.log"}) == "api/log/path_build_2Fa_b.log.txt"
