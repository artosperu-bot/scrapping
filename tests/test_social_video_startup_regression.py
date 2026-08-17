from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE_PATH = ROOT / "src" / "product_intelligence" / "social_video_visibility.py"


def test_social_video_before_target_is_snapshotted_before_new_widget_exists():
    """The new social widget must never be eligible as its own pack(before=...) target."""
    source = SOURCE_PATH.read_text(encoding="utf-8")
    siblings_pos = source.index('children = list(search_tab.winfo_children())')
    create_pos = source.index('social_box = ttk.LabelFrame(search_tab')
    assert siblings_pos < create_pos


def test_final_exe_shell_contains_social_video_visibility_mixin():
    source = (ROOT / "src" / "product_intelligence" / "final_live_ui_desktop.py").read_text(encoding="utf-8")
    assert "SocialVideoVisibilityMixin" in source
