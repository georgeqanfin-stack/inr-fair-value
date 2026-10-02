from inrfv.io import raw_checksums, sha256_file, verify_raw_manifest, write_raw_manifest


def test_text_hash_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_bytes(b"date,value\n2026-01-01,1\n")
    b.write_bytes(b"date,value\r\n2026-01-01,1\r\n")
    assert sha256_file(a) == sha256_file(b)
    c, d = tmp_path / "c.bin", tmp_path / "d.bin"
    c.write_bytes(b"x\n")
    d.write_bytes(b"x\r\n")
    assert sha256_file(c) != sha256_file(d)                 # binary files stay byte-exact


def test_manifest_skips_local_only_files_and_survives_crlf_checkout(tmp_path):
    (tmp_path / "dbie").mkdir()
    (tmp_path / "manual" / "imf_eba").mkdir(parents=True)
    (tmp_path / "ewn").mkdir()
    (tmp_path / "dbie" / "x.csv").write_bytes(b"date,value\n2026-01-01,1\n")
    (tmp_path / "manual" / "imf_eba" / "table.pdf").write_bytes(b"%PDF")
    (tmp_path / "ewn" / "book.xlsx").write_bytes(b"PK")
    assert list(raw_checksums(tmp_path)) == ["dbie/x.csv"]
    write_raw_manifest(tmp_path)
    (tmp_path / "manual" / "imf_eba" / "table.pdf").unlink()            # a fresh clone lacks it
    (tmp_path / "dbie" / "x.csv").write_bytes(b"date,value\r\n2026-01-01,1\r\n")
    chk = verify_raw_manifest(tmp_path)
    assert not chk["changed"] and not chk["removed"] and not chk["added"]
