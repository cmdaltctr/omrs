"""Pure rules for model search and download (tasks 2.1 to 2.3).

Covers the name rules, the quantisation label parser, the split grouping and
the built-in Ollama names of ``core/providers/model_sources.py``.
"""

from __future__ import annotations

import pytest

from omrs.core.providers import model_sources as ms

# --- 2.1 name rules ---------------------------------------------------------

BAD_REPO_IDS = [
    "../x",
    "x/..",
    "./x",
    "org/",
    "/name",
    "name",
    "a b",
    "a b/c",
    "--help",
    "-org/name",
    "org/-name",
    "org/name;ls",
    "org/name/extra",
    "org/na me",
    "",
    "org\n/name",
]


@pytest.mark.parametrize(
    "value", ["Qwen/Qwen3-4B-GGUF", "unsloth/Qwen3-4B-GGUF", "a/b", "o_1.x/n-2.y"]
)
def test_a_repo_id_in_org_name_form_is_accepted(value: str) -> None:
    assert ms.is_valid_repo_id(value)


@pytest.mark.parametrize("value", BAD_REPO_IDS)
def test_a_malformed_repo_id_is_refused(value: str) -> None:
    assert not ms.is_valid_repo_id(value)


@pytest.mark.parametrize("value", ["Q4_K_M", "UD-Q4_K_XL", "Q8_0", "BF16", "x"])
def test_a_label_of_letters_digits_underscore_and_hyphen_is_accepted(value: str) -> None:
    assert ms.is_valid_label(value)


@pytest.mark.parametrize("value", ["", "-Q4", "--help", "a b", "Q4;ls", "../x", "Q4.K", "a/b"])
def test_a_malformed_label_is_refused(value: str) -> None:
    assert not ms.is_valid_label(value)


@pytest.mark.parametrize(
    "value",
    [
        "qwen3",
        "qwen3:0.6b",
        "qwen3:latest",
        "nomic-embed-text",
        "library/qwen3:4b",
        "hf.co/unsloth/Qwen3-4B-GGUF",
        "hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M",
    ],
)
def test_the_four_ollama_name_forms_are_accepted(value: str) -> None:
    assert ms.is_valid_ollama_name(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a b",
        "qwen3;ls",
        "-qwen3",
        "--help",
        "../x",
        "qwen3:",
        "qwen3:-x",
        "a/b/c:tag",
        "hf.co/unsloth",
        "hf.co/../x:Q4",
        "hf.co/-org/name",
        "hf.co/org/name:Q4 K",
        "qwen3\n",
    ],
)
def test_a_malformed_ollama_name_is_refused(value: str) -> None:
    assert not ms.is_valid_ollama_name(value)


@pytest.mark.parametrize("value", ["qwen3", "q", "x" * 100, "Qwen 3 4B", "نموذج"])
def test_a_query_of_one_to_100_characters_is_accepted(value: str) -> None:
    assert ms.is_valid_query(value)


@pytest.mark.parametrize("value", ["", "x" * 101, "a\nb", "a\x00b", "a\tb", "a\x7fb"])
def test_an_empty_long_or_control_character_query_is_refused(value: str) -> None:
    assert not ms.is_valid_query(value)


def test_value_builders_join_repo_and_label() -> None:
    assert ms.hf_model_value("unsloth/Qwen3-4B-GGUF", "Q4_K_M") == "unsloth/Qwen3-4B-GGUF:Q4_K_M"
    assert ms.ollama_hf_name("unsloth/Qwen3-4B-GGUF", "Q4_K_M") == (
        "hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M"
    )


# --- 2.2 label parser and grouping -----------------------------------------


@pytest.mark.parametrize(
    ("filename", "label"),
    [
        ("Qwen3-4B-Q4_K_M.gguf", "Q4_K_M"),
        ("Qwen3-4B-UD-Q4_K_XL.gguf", "UD-Q4_K_XL"),
        ("Qwen3-4B-Q8_0.gguf", "Q8_0"),
        ("Qwen3-4B-Q8_0-00001-of-00002.gguf", "Q8_0"),
        ("model-IQ4_XS.gguf", "IQ4_XS"),
        ("model-Q6_K.gguf", "Q6_K"),
        ("model-MXFP4_MOE.gguf", "MXFP4_MOE"),
        ("model-MXFP4.gguf", "MXFP4"),
        ("model-BF16.gguf", "BF16"),
        ("model-F16.gguf", "F16"),
        ("model-TQ1_0.gguf", "TQ1_0"),
        ("model.Q5_K_S.gguf", "Q5_K_S"),
        ("sub/dir/model-Q4_0.gguf", "Q4_0"),
        ("qwen3-4b-q4_k_m.gguf", "Q4_K_M"),
    ],
)
def test_the_parser_reads_the_quantisation_label(filename: str, label: str) -> None:
    assert ms.parse_quant_label(filename) == label


@pytest.mark.parametrize(
    "filename",
    [
        "mmproj-F16.gguf",
        "Qwen3-VL-mmproj-Q8_0.gguf",
        "model.gguf",
        "model-custom.gguf",
        "README.md",
        "model-Q4_K_M.bin",
        "modelQ4_K_M.gguf",
        "model-XQ4_K_M.gguf",
    ],
)
def test_the_parser_gives_none_for_projectors_unknown_labels_and_other_files(
    filename: str,
) -> None:
    assert ms.parse_quant_label(filename) is None


def test_two_split_parts_form_one_entry_with_the_summed_size() -> None:
    entries = ms.group_gguf_files(
        [
            ("model-Q8_0-00002-of-00002.gguf", 700),
            ("model-Q8_0-00001-of-00002.gguf", 500),
        ]
    )
    assert entries == [
        ms.QuantEntry(
            label="Q8_0",
            files=("model-Q8_0-00001-of-00002.gguf", "model-Q8_0-00002-of-00002.gguf"),
            size_bytes=1200,
        )
    ]


def test_grouping_drops_projector_and_unlabelled_files_and_orders_by_size() -> None:
    entries = ms.group_gguf_files(
        [
            ("model-Q8_0.gguf", 800),
            ("mmproj-F16.gguf", 50),
            ("model-Q4_K_M.gguf", 400),
            ("model.gguf", 9),
            ("model-UD-Q4_K_XL.gguf", 450),
        ]
    )
    assert [(e.label, e.files, e.size_bytes) for e in entries] == [
        ("Q4_K_M", ("model-Q4_K_M.gguf",), 400),
        ("UD-Q4_K_XL", ("model-UD-Q4_K_XL.gguf",), 450),
        ("Q8_0", ("model-Q8_0.gguf",), 800),
    ]


def test_grouping_nothing_gives_an_empty_list() -> None:
    assert ms.group_gguf_files([]) == []


def _entry(label: str, size: int) -> ms.QuantEntry:
    return ms.QuantEntry(label=label, files=(f"m-{label}.gguf",), size_bytes=size)


def test_the_preferred_label_is_q4_k_m_when_present() -> None:
    entries = [_entry("Q4_K_S", 1), _entry("Q4_K_M", 5), _entry("Q8_0", 9)]
    assert ms.preferred_label(entries) == "Q4_K_M"


def test_without_q4_k_m_the_preferred_label_is_the_smallest_at_four_bits_or_more() -> None:
    entries = [_entry("Q2_K", 1), _entry("Q3_K_M", 2), _entry("Q8_0", 9), _entry("Q5_K_M", 6)]
    assert ms.preferred_label(entries) == "Q5_K_M"


def test_the_preferred_label_is_none_when_every_entry_is_below_four_bits() -> None:
    assert ms.preferred_label([_entry("Q2_K", 1), _entry("IQ3_S", 2)]) is None
    assert ms.preferred_label([]) is None


def test_the_full_quality_label_is_q8_0() -> None:
    assert ms.FULL_QUALITY_LABEL == "Q8_0"


# --- 2.3 built-in Ollama names ---------------------------------------------


def test_the_built_in_ollama_names_are_a_short_fixed_tuple_of_valid_names() -> None:
    names = ms.OLLAMA_LIBRARY_NAMES
    assert isinstance(names, tuple)
    assert 8 <= len(names) <= 16
    assert len(set(names)) == len(names)
    assert all(ms.is_valid_ollama_name(n) for n in names)
    assert {"qwen3", "qwen3-embedding", "nomic-embed-text"} <= set(names)


def test_the_ollama_filter_returns_names_that_contain_the_query_in_list_order() -> None:
    assert ms.filter_ollama_names("qwen3") == [n for n in ms.OLLAMA_LIBRARY_NAMES if "qwen3" in n]
    assert len(ms.filter_ollama_names("qwen3")) >= 2


def test_the_ollama_filter_matches_inside_a_name_not_only_at_the_start() -> None:
    found = ms.filter_ollama_names("embed")
    assert "nomic-embed-text" in found
    assert "qwen3-embedding" in found
    assert found == [n for n in ms.OLLAMA_LIBRARY_NAMES if "embed" in n]


def test_the_ollama_filter_ignores_case_and_returns_nothing_for_an_unknown_query() -> None:
    assert ms.filter_ollama_names("QWEN3") == ms.filter_ollama_names("qwen3")
    assert ms.filter_ollama_names("zzz-no-such-model") == []


# --- 6.2 revision rule -----------------------------------------------------


def test_a_revision_is_exactly_forty_lower_case_hex_characters() -> None:
    assert ms.is_valid_revision("0123456789abcdef0123456789abcdef01234567")
    assert not ms.is_valid_revision("0123456789ABCDEF0123456789ABCDEF01234567")
    assert not ms.is_valid_revision("main")
    assert not ms.is_valid_revision("0123456789abcdef0123456789abcdef0123456")
    assert not ms.is_valid_revision("0123456789abcdef0123456789abcdef012345678")
    assert not ms.is_valid_revision("0123456789abcdef0123456789abcdef0123456\n")
    assert not ms.is_valid_revision("../../0123456789abcdef0123456789abcdef01")
