import configparser
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from install_kwin_rules import STALE_RULE_KEYS, apply_rule_keys


def _make_rule(**keys):
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    config['42'] = {}
    for k, v in keys.items():
        config['42'][k] = v
    return config['42']


class TestApplyRuleKeys:
    def test_writes_noborder_keys(self):
        rule = _make_rule()
        apply_rule_keys(rule, 'alacritty-pos-1920_0', 'Alacritty Maximize at 1920,0')
        assert rule['wmclass'] == 'alacritty-pos-1920_0'
        assert rule['wmclassmatch'] == '1'
        assert rule['noborder'] == 'true'
        assert rule['noborderrule'] == '2'
        assert rule['Description'] == 'Alacritty Maximize at 1920,0'

    def test_does_not_write_position_or_maximize_keys(self):
        rule = _make_rule()
        apply_rule_keys(rule, 'alacritty-pos-0_0', 'x')
        for stale in ('position', 'positionrule',
                      'maximizevert', 'maximizevertrule',
                      'maximizehoriz', 'maximizehorizrule'):
            assert stale not in rule, f"{stale} should not be set by apply_rule_keys"

    def test_strips_stale_keys_from_prior_install(self):
        rule = _make_rule(
            Description='old',
            wmclass='alacritty-pos-1920_0',
            wmclassmatch='1',
            position='1920,0',
            positionrule='4',
            maximizevert='true',
            maximizevertrule='4',
            maximizehoriz='true',
            maximizehorizrule='4',
            activity='All Desktops',
            activityrule='4',
            screen='1',
            screenrule='2',
            noborder='true',
            noborderrule='2',
        )
        apply_rule_keys(rule, 'alacritty-pos-1920_0', 'new desc')
        for stale in STALE_RULE_KEYS:
            assert stale not in rule, f"{stale} should be stripped"
        assert rule['Description'] == 'new desc'
        assert rule['noborder'] == 'true'
        assert rule['noborderrule'] == '2'

    def test_idempotent_on_already_clean_rule(self):
        rule = _make_rule(
            Description='x', wmclass='alacritty-pos-0_0', wmclassmatch='1',
            noborder='true', noborderrule='2',
        )
        apply_rule_keys(rule, 'alacritty-pos-0_0', 'x')
        apply_rule_keys(rule, 'alacritty-pos-0_0', 'x')
        assert rule['noborder'] == 'true'
        assert rule['noborderrule'] == '2'
        for stale in STALE_RULE_KEYS:
            assert stale not in rule
