from __future__ import annotations

from pulse_aws.reaper_lambda import get_listener_rules_map


class FakeElbv2Client:
	def describe_rules(self, *, ListenerArn: str):
		assert ListenerArn == "arn:listener"
		return {
			"Rules": [
				{
					"Priority": "default",
					"RuleArn": "arn:default",
					"Conditions": [],
					"Actions": [],
				},
				{
					"Priority": "140",
					"RuleArn": "arn:header",
					"Conditions": [
						{
							"Field": "http-header",
							"HttpHeaderConfig": {
								"HttpHeaderName": "X-Pulse-Render-Affinity",
								"Values": ["test-20260306-151500Z"],
							},
						}
					],
					"Actions": [{"TargetGroupArn": "arn:target-group"}],
				},
			]
		}


def test_get_listener_rules_map_collects_header_rules():
	rules_map = get_listener_rules_map(FakeElbv2Client(), "arn:listener")

	assert rules_map == {
		"test-20260306-151500Z": {
			"rule_arns": ["arn:header"],
			"target_group_arn": "arn:target-group",
		}
	}
