from custom_components.spielpartner_aufnahme import logic


def test_norm_and_match():
    assert logic.norm("Hölenblick") == "hoelenblick"
    assert logic.match_filters(
        "Hoelenblick", [("switch.a_hoelenblick_x", "Quelle Hoelenblick Hauptstream"), ("switch.b_fuchsblick", "Fuchsblick")]
    ) == ["switch.a_hoelenblick_x"]


def test_names_and_format():
    assert logic.parse_folder_name("Spielen mit Frank Visselff #03") == ("Frank Visselff", 3)
    assert logic.parse_folder_name("") == (None, None)
    assert logic.partner_folder("Spielen mit", "Frank", 1) == "Spielen mit Frank #01"
    assert logic.season_folder(2, "08,10,2026") == "Saison 02 vom 08,10,2026"
    assert logic.file_format(1, 2, 3, "FB", 4, " (4K) %DD.%MM.%CCYY") == "#01.02.03.FB.04 (4K) %DD.%MM.%CCYY"
    assert logic.file_format(1, 2, 3, "Cam ID", 104) == "#01.02.03.Cam ID.104"


def test_new_day():
    today = "Saison 01 vom 08,10,2026"
    assert not logic.is_new_day([], today)
    assert not logic.is_new_day(["(keine Unterordner)"], today)
    assert not logic.is_new_day([today, "Saison 01 vom 01,10,2026"], today)
    assert logic.is_new_day(["Saison 01 vom 01,10,2026"], today)


def test_paths_and_thread():
    assert logic.join_unix("X:/a/", "b", "c") == "X:/a/b/c"
    assert logic.join_win("X:\\a", "b") == "X:\\a\\b"
    assert logic.unpack_thread("123|02") == ("123", "02")
    assert logic.unpack_thread("unknown") == ("", "")
    assert logic.pack_thread("9", 3) == "9|03"
    assert logic.valid_kennung("frank_visselff") and not logic.valid_kennung("Frank X")


def test_post_texts():
    assert "40%" in logic.build_post_header(5, 40)
    assert "unbekannt" in logic.build_post_header(5, None)
    assert logic.build_cam_caption("Fuchsblick", "#01.02.03.FB.04") == "**Fuchsblick**: `#01.02.03.FB.04`"
