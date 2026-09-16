from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CORE = ROOT / "core"
CLI = ROOT / "cli" / "model-private-skill.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(CORE))

import validate_output  # noqa: E402
from model_private_skill import calculate_request, validate_request  # noqa: E402


def run_json(script: str, *args: str, expect_success: bool = True):
    process = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if expect_success and process.returncode != 0:
        raise AssertionError(process.stderr)
    if not expect_success:
        return process
    return json.loads(process.stdout)


def run_universal_cli(
    *args: str, stdin_payload: dict | None = None, expect_success: bool = True
):
    process = subprocess.run(
        [sys.executable, str(CLI), *args],
        input=json.dumps(stdin_payload) if stdin_payload is not None else None,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if expect_success and process.returncode != 0:
        raise AssertionError(process.stderr)
    if not expect_success:
        return process
    return json.loads(process.stdout)


def platform_request() -> dict:
    return {
        "schema_version": "1.0",
        "model": {
            "id": "example/7b",
            "revision": "abc123",
            "architecture": "dense",
            "parameters_b": 7,
            "active_parameters_b": None,
            "artifact_gb": 15,
            "attention": {
                "kind": "generic",
                "layers": 32,
                "kv_heads": 8,
                "head_dim": 128,
                "kv_bytes_per_token": None,
            },
        },
        "workload": {
            "typical_input_tokens": 2000,
            "max_input_tokens": 8000,
            "typical_output_tokens": 512,
            "max_output_tokens": 2000,
            "typical_active_concurrency": 8,
            "peak_active_concurrency": 32,
            "peak_duration_hours_per_day": 1,
            "max_length_concurrency": None,
            "typical_rps": None,
            "peak_rps": None,
            "typical_response_rps": None,
            "peak_response_rps": None,
        },
        "slo": {
            "ttft_ms_p95": 2000,
            "output_tps_per_request": 30,
        },
        "precision": {
            "economic_weight_bits": 16,
            "peak_production_weight_bits": 16,
            "economic_kv_bits": 16,
            "peak_production_kv_bits": 16,
            "quantization_policy": "preserve",
        },
        "hardware_profile": {
            "gpu_vram_gb": 80,
            "max_gpus_per_node": 8,
            "supported_parallel_degrees": [1, 2, 4, 8, 16],
        },
        "engineering": {
            "workspace_ratio": 0.2,
            "bytes_per_token": 4,
            "protocol_overhead": 1.3,
            "response_mode": "streaming",
            "failure_retains_full_peak": False,
        },
        "benchmarks": {},
    }


class MemoryTests(unittest.TestCase):
    def test_moe_uses_total_resident_parameters(self):
        result = run_json(
            "estimate_memory.py",
            "--parameters-b",
            "671",
            "--architecture",
            "moe",
            "--active-parameters-b",
            "37",
            "--layers",
            "61",
            "--kv-heads",
            "8",
            "--head-dim",
            "128",
            "--economic-weight-bits",
            "8",
            "--peak-production-weight-bits",
            "16",
            "--typical-live-tokens",
            "10000",
            "--peak-live-tokens",
            "20000",
            "--gpu-vram-gb",
            "192",
        )
        self.assertEqual(
            result["parameters"]["weight_memory_basis"], "resident_total_b"
        )
        self.assertEqual(result["tiers"]["economic"]["weight_gb"], 671)
        self.assertEqual(result["tiers"]["peak_production"]["weight_gb"], 1342)

    def test_special_attention_requires_override(self):
        process = run_json(
            "estimate_memory.py",
            "--parameters-b",
            "100",
            "--attention-kind",
            "mla",
            "--economic-weight-bits",
            "8",
            "--peak-production-weight-bits",
            "16",
            "--typical-live-tokens",
            "1000",
            "--peak-live-tokens",
            "2000",
            "--gpu-vram-gb",
            "80",
            expect_success=False,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("special attention requires", process.stderr)


class CapacityTests(unittest.TestCase):
    BASE_ARGS = (
        "--model-id",
        "example/7b",
        "--model-revision",
        "abc123",
        "--parameters-b",
        "7",
        "--layers",
        "32",
        "--kv-heads",
        "8",
        "--head-dim",
        "128",
        "--economic-weight-bits",
        "16",
        "--peak-production-weight-bits",
        "16",
        "--typical-input-tokens",
        "2000",
        "--max-input-tokens",
        "8000",
        "--typical-output-tokens",
        "512",
        "--max-output-tokens",
        "2000",
        "--typical-concurrency",
        "8",
        "--peak-concurrency",
        "32",
        "--peak-hours-per-day",
        "1",
        "--target-ttft-ms-p95",
        "2000",
        "--target-output-tps-per-request",
        "30",
        "--quantization-policy",
        "preserve",
        "--model-artifact-gb",
        "15",
        "--gpu-vram-gb",
        "80",
    )

    def test_two_tiers_and_arithmetic(self):
        result = run_json("capacity_plan.py", *self.BASE_ARGS)
        economic = result["tiers"]["economic"]
        peak = result["tiers"]["peak_production"]
        self.assertEqual(economic["gpu_capacity"]["replicas"], 1)
        self.assertEqual(peak["gpu_capacity"]["replicas"], 2)
        for tier in (economic, peak):
            capacity = tier["gpu_capacity"]
            self.assertEqual(
                capacity["total_gpus"],
                capacity["gpus_per_replica"] * capacity["replicas"],
            )
            self.assertEqual(tier["performance_status"], "benchmark_required")
        for tier in (economic, peak):
            network = tier["node_configuration"]
            self.assertIsNone(network["public_access_ingress_peak_mbps"])
            self.assertIsNone(network["public_access_bandwidth_mbps"])
            self.assertGreater(network["public_access_egress_peak_mbps"], 0)
            self.assertEqual(network["public_access_response_mode"], "streaming")
        self.assertGreater(result["request_summary"]["typical_rps"], 0)
        self.assertEqual(
            result["request_summary"]["typical_rps_basis"],
            "derived_from_concurrency_and_duration",
        )

    def test_public_bandwidth_uses_response_mode_specific_formula(self):
        shared = list(self.BASE_ARGS) + [
            "--typical-rps",
            "2",
            "--peak-rps",
            "8",
        ]
        streaming = run_json("capacity_plan.py", *shared)
        streaming_peak = streaming["tiers"]["peak_production"]["node_configuration"]
        self.assertEqual(streaming_peak["public_access_response_mode"], "streaming")
        self.assertEqual(streaming_peak["public_access_ingress_peak_mbps"], 2.662)
        self.assertEqual(streaming_peak["public_access_egress_peak_mbps"], 0.04)
        self.assertEqual(streaming_peak["public_access_bandwidth_mbps"], 2.662)

        non_streaming = run_json(
            "capacity_plan.py",
            *shared,
            "--response-mode",
            "non_streaming",
            "--typical-response-rps",
            "3",
            "--peak-response-rps",
            "40",
        )
        non_streaming_peak = non_streaming["tiers"]["peak_production"][
            "node_configuration"
        ]
        self.assertEqual(
            non_streaming_peak["public_access_response_mode"], "non_streaming"
        )
        self.assertEqual(non_streaming_peak["public_access_egress_peak_mbps"], 3.328)
        self.assertEqual(non_streaming_peak["public_access_bandwidth_mbps"], 3.328)
    def test_invalid_length_order_is_rejected(self):
        args = list(self.BASE_ARGS)
        args[args.index("--max-input-tokens") + 1] = "1000"
        process = run_json(
            "capacity_plan.py", *args, expect_success=False
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("cannot be smaller", process.stderr)

    def test_performance_benchmark_drives_replica_count(self):
        result = run_json(
            "capacity_plan.py",
            *self.BASE_ARGS,
            "--economic-benchmark-prefill-tps",
            "500",
            "--economic-benchmark-decode-tps",
            "100",
            "--economic-benchmark-gpus-per-replica",
            "1",
            "--economic-benchmark-match",
            "exact",
            "--peak-production-benchmark-prefill-tps",
            "1000",
            "--peak-production-benchmark-decode-tps",
            "300",
            "--peak-production-benchmark-gpus-per-replica",
            "1",
            "--peak-production-benchmark-match",
            "similar",
        )
        self.assertEqual(
            result["tiers"]["economic"]["performance_status"], "verified"
        )
        self.assertGreater(
            result["tiers"]["economic"]["gpu_capacity"]["replicas"], 1
        )
        self.assertEqual(
            result["tiers"]["peak_production"]["performance_status"], "estimated"
        )

    def test_peak_duration_changes_idle_reference_not_peak_capacity(self):
        short_args = list(self.BASE_ARGS)
        short_args[short_args.index("--peak-hours-per-day") + 1] = "0.25"
        long_args = list(self.BASE_ARGS)
        long_args[long_args.index("--peak-hours-per-day") + 1] = "12"
        short = run_json("capacity_plan.py", *short_args)
        long = run_json("capacity_plan.py", *long_args)
        self.assertLess(
            short["load_normalization"]["daily_equivalent_concurrency"],
            long["load_normalization"]["daily_equivalent_concurrency"],
        )
        self.assertEqual(
            short["tiers"]["peak_production"]["gpu_capacity"]["total_gpus"],
            long["tiers"]["peak_production"]["gpu_capacity"]["total_gpus"],
        )

    def test_long_context_reports_card_count_range(self):
        args = list(self.BASE_ARGS)
        replacements = {
            "--parameters-b": "70",
            "--layers": "80",
            "--kv-heads": "8",
            "--head-dim": "128",
            "--max-input-tokens": "131072",
            "--max-output-tokens": "8192",
            "--peak-concurrency": "128",
            "--model-artifact-gb": "145",
        }
        for key, value in replacements.items():
            args[args.index(key) + 1] = value
        result = run_json("capacity_plan.py", *args)
        low, high = result["max_length_safety"][
            "gpus_per_replica_by_memory_range"
        ]
        self.assertGreaterEqual(high, low)
        self.assertIsNone(
            result["max_length_safety"]["max_length_concurrency_supplied"]
        )

    def test_special_attention_with_measured_kv(self):
        args = list(self.BASE_ARGS)
        args.extend(
            [
                "--attention-kind",
                "mla",
                "--kv-bytes-per-token",
                "131072",
            ]
        )
        result = run_json("capacity_plan.py", *args)
        self.assertEqual(
            result["tiers"]["economic"]["memory"]["kv_calculation_basis"],
            "official_or_measured_override",
        )


class PlatformNeutralInterfaceTests(unittest.TestCase):
    def test_python_api(self):
        request = platform_request()
        self.assertEqual(validate_request(request), [])
        result = calculate_request(request)
        self.assertEqual(result["calculation_version"], "1.3")
        self.assertEqual(result["tiers"]["peak_production"]["gpu_capacity"]["replicas"], 2)

    def test_json_cli(self):
        result = run_universal_cli(
            "calculate",
            "--input",
            "-",
            stdin_payload=platform_request(),
        )
        self.assertEqual(result["request_summary"]["model_id"], "example/7b")
        self.assertIn("economic", result["tiers"])

    def test_validate_input_cli(self):
        result = run_universal_cli(
            "validate-input",
            "--input",
            "-",
            stdin_payload=platform_request(),
        )
        self.assertTrue(result["valid"])

    def test_unknown_platform_field_is_rejected(self):
        request = platform_request()
        request["codex_thread_id"] = "not-portable"
        errors = validate_request(request)
        self.assertTrue(any("unsupported" in item for item in errors))


class CatalogTests(unittest.TestCase):
    def test_catalog_validates(self):
        result = run_json("gpu_catalog.py", "validate")
        self.assertTrue(result["valid"])
        self.assertGreaterEqual(result["device_count"], 8)

    def test_filter_is_limited_and_does_not_select_incomplete_precision(self):
        result = run_json(
            "gpu_catalog.py",
            "filter",
            "--min-vram-gb",
            "40",
            "--precision",
            "BF16",
            "--max-results",
            "5",
        )
        self.assertLessEqual(len(result["candidates"]), 5)
        ids = {item["catalog_id"] for item in result["candidates"]}
        self.assertNotIn("metax-c500-pcie-64gb", ids)

    def test_zero_vram_is_rejected(self):
        process = run_json(
            "gpu_catalog.py",
            "filter",
            "--min-vram-gb",
            "0",
            "--precision",
            "BF16",
            expect_success=False,
        )
        self.assertNotEqual(process.returncode, 0)

    def test_same_name_variants_are_exact(self):
        result = run_json(
            "gpu_catalog.py",
            "filter",
            "--min-vram-gb",
            "75",
            "--precision",
            "BF16",
            "--vendor",
            "NVIDIA",
        )
        for item in result["candidates"]:
            form_family = (
                "SXM" if item["form_factor"].upper().startswith("SXM") else "PCIE"
            )
            self.assertIn(form_family, item["catalog_id"].upper())


def valid_plan(tier: str, replicas: int) -> dict:
    total_nodes = replicas
    return {
        "tier": tier,
        "precision": {
            "weights": "BF16",
            "kv_cache": "BF16",
            "quantization_scheme": None,
            "quality_validation_required": False,
        },
        "deployment_framework": {
            "name": "vLLM",
            "version_or_commit": None,
            "reason": "supported serving framework",
            "required_features": ["continuous batching"],
            "evidence_ids": ["E1"],
        },
        "gpu_requirements": {
            "gpus_per_replica": 1,
            "gpus_per_replica_by_memory": 1,
            "gpus_per_replica_by_performance": None,
            "replicas": replicas,
            "total_gpus": replicas,
            "minimum_vram_per_gpu_gb": 80,
            "required_vram_per_replica_gb": 20,
            "aggregate_nominal_vram_per_replica_gb": 80,
            "required_precision_features": ["BF16"],
            "intra_node_interconnect": "PCIe",
            "inter_node_rdma_required": False,
            "minimum_inter_node_bandwidth_gbps": None,
        },
        "gpu_candidates": [
            {
                "catalog_id": "nvidia-h100-sxm-80gb",
                "vendor": "NVIDIA",
                "model": "H100",
                "form_factor": "SXM",
                "vram_gb": 80,
                "quantity_per_replica": 1,
                "evidence_ids": ["E1"],
                "notes": "capacity candidate",
            }
        ],
        "node_configuration": {
            "gpus_per_node": 1,
            "nodes_per_replica": 1,
            "total_nodes": total_nodes,
            "vcpu_per_node": 32,
            "total_vcpu": 32 * total_nodes,
            "memory_gb_per_node": 256,
            "total_memory_gb": 256 * total_nodes,
            "system_disk_gb_per_node": 200,
            "total_system_disk_gb": 200 * total_nodes,
            "model_disk_gb_per_node": 100,
            "total_model_disk_gb": 100 * total_nodes,
            "shared_storage_gb": 100,
            "public_access_ingress_peak_mbps": 1.0,
            "public_access_egress_peak_mbps": 0.5,
            "public_access_bandwidth_mbps": 1000,
            "public_access_response_mode": "streaming",
        },
        "topology": {
            "tensor_parallel": 1,
            "pipeline_parallel": 1,
            "data_parallel": replicas,
            "replicas": replicas,
            "load_balancing": "none" if replicas == 1 else "active-active",
            "failure_mode": "degraded after one replica fails",
        },
        "expected_performance": {
            "status": "benchmark_required",
            "ttft_ms_p95": None,
            "itl_ms_p95": None,
            "output_tps_per_request": None,
            "prefill_tps_total": None,
            "decode_tps_total": None,
            "evidence_ids": [],
        },
        "confidence": "low",
    }


class OutputValidationTests(unittest.TestCase):
    def test_json_schema_file_parses(self):
        schema = json.loads(
            (
                ROOT
                / "core"
                / "model_private_skill"
                / "schemas"
                / "output-schema.json"
            ).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])

    def test_input_schema_file_parses(self):
        schema = json.loads(
            (
                ROOT
                / "core"
                / "model_private_skill"
                / "schemas"
                / "input-schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")

    def test_only_one_agentskills_entry_exists(self):
        skill_files = list(ROOT.rglob("SKILL.md"))
        self.assertEqual(skill_files, [ROOT / "SKILL.md"])

    def test_root_skill_is_platform_neutral_and_links_source_policy(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Codex", content)
        self.assertNotIn("OpenClaw", content)
        self.assertIn("source-policy.md", content)

    def test_html_template_fixes_resource_table_layout(self):
        template = (
            ROOT
            / "core"
            / "model_private_skill"
            / "references"
            / "html-output-template.md"
        ).read_text(encoding="utf-8")
        table = template[template.index("<table>") : template.index("</table>")]
        self.assertIn("<caption>", table)
        self.assertIn("<!doctype html>", template)
        self.assertIn('<meta charset="utf-8">', template)
        self.assertIn('<main class="plan">', template)
        self.assertIn("证据来源", template)
        self.assertLess(template.index("</table>"), template.index("<h2>GPU 选型建议</h2>"))
        self.assertLess(table.index('<tr><th scope="row">'), table.index('<tr><th scope="row">GPU'))
        self.assertLess(table.index('<tr><th scope="row">GPU'), table.index("</tbody>"))
        self.assertEqual(table.count('scope="col"'), 5)
        self.assertIn('data-category="planning-baseline"', table)
        self.assertIn('data-category="resource-advice"', table)
        self.assertIn('data-category="deployment-advice"', table)
        self.assertIn('data-row="service-scenario"', table)
        self.assertIn('data-section="model-facts"', template)
        self.assertIn('data-section="technical-terms"', template)
        self.assertIn("混合注意力/特殊算子", template)

        self.assertIn('class="table-note"', template)
        self.assertIn('GPU推荐', table)
        self.assertLess(table.index("显存容量"), table.index("GPU推荐"))
        self.assertLess(table.index("GPU推荐"), table.index("CPU"))
        self.assertIn('<strong>说明</strong>', template)
        self.assertNotIn("特殊说明", template)
        self.assertIn('data-section="resource-estimates"', template)
        self.assertIn("简单推算路径", template)
        self.assertIn("精细推算路径", template)
        self.assertIn("压测与验收计划", template)
        self.assertIn("每一个数字都必须", template)
        self.assertIn('class="estimate-note"', template)
        self.assertIn('<strong>输入：</strong>', template)
        self.assertIn('<strong>估算过程：</strong>', template)
        self.assertIn('<strong>结果：</strong>', template)
        self.assertNotIn("计算输入", template)
        self.assertNotIn("计算结果", template)
        self.assertNotIn("结果与表格对应", template)
        for title in (
            "1. 显存容量：",
            "2. CPU：",
            "3. 内存：",
            "4. 系统盘：",
            "5. 模型盘：",
            "6. 共享存储：",
            "7. 公网带宽（用户接入）：",
        ):
            self.assertIn(title, template)
        vram_row = table[
            table.index('<th scope="row">显存容量')
            : table.index("</tr>", table.index('<th scope="row">显存容量'))
        ]
        self.assertIn("每推理副本所需 GPU 显存", vram_row)
        self.assertNotIn("GPU 型号", vram_row)
        self.assertNotIn("status</th>", table)

    def test_qwen_example_keeps_vram_objective_and_inputs_traceable(self):
        sample = (ROOT / "qwen3.8-27b-deployment-plan.html").read_text(
            encoding="utf-8"
        )
        table = sample[sample.index("<table>") : sample.index("</table>")]
        vram_row = table[
            table.index('<th scope="row">显存容量')
            : table.index("</tr>", table.index('<th scope="row">显存容量'))
        ]
        self.assertIn("每推理副本至少", vram_row)
        self.assertNotIn("H100", vram_row)
        self.assertNotIn("H200", vram_row)
        self.assertIn("简单推算路径", sample)
        self.assertIn("精细推算路径", sample)
        self.assertIn("65,536 bytes/Token", sample)
        self.assertIn("16 × 4 × 256", sample)
        self.assertIn("48 个 Gated DeltaNet + 16 个 Gated Attention", sample)
        self.assertIn('data-section="technical-terms"', sample)
        self.assertIn("20% 余量", sample)
        self.assertIn('<strong>说明</strong>', sample)
        self.assertIn('class="estimate-note"', sample)
        self.assertIn('<strong>输入：</strong>', sample)
        self.assertIn('<strong>估算过程：</strong>', sample)
        self.assertIn('<strong>结果：</strong>', sample)
        self.assertNotIn("计算输入", sample)
        self.assertNotIn("计算结果", sample)
        self.assertNotIn("结果与表格对应", sample)
        self.assertIn("1. 显存容量：", sample)
        self.assertIn("公网带宽（用户接入）", table)

        self.assertIn("7. 公网带宽（用户接入）：", sample)
        self.assertIn("<strong>范围说明：</strong>本项仅估算公网用户接入带宽", sample)
        self.assertIn("服务私网带宽用于", sample)
        self.assertIn("若同一推理副本采用跨节点 TP/PP", sample)

    def test_output_schema_requires_source_classification(self):
        schema = json.loads(
            (
                ROOT
                / "core"
                / "model_private_skill"
                / "schemas"
                / "output-schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.5")
        required = schema["$defs"]["evidence"]["required"]
        self.assertIn("publisher", required)
        self.assertIn("source_type", required)

    def payload(self) -> dict:
        return {
            "schema_version": "1.5",
            "request_summary": {
                "model_id": "example/7b",
                "model_revision": "abc123",
                "typical_input_tokens": 2000,
                "max_input_tokens": 8000,
                "typical_output_tokens": 512,
                "max_output_tokens": 2000,
                "typical_active_concurrency": 8,
                "peak_active_concurrency": 32,
                "peak_duration_hours_per_day": 1,
                "typical_rps": 0.42,
                "peak_rps": 1.68,
                "response_mode": "streaming",
                "typical_response_rps": None,
                "peak_response_rps": None,
                "target_ttft_ms_p95": 2000,
                "target_output_tps_per_request": 25,
                "derived_target_itl_ms": 40,
                "quantization_policy": "preserve",
            },
            "assumptions": [],
            "evidence": [
                {
                    "id": "E1",
                    "category": "gpu",
                    "publisher": "Example GPU Vendor",
                    "source_type": "official_datasheet",
                    "title": "official",
                    "url": "https://example.invalid",
                    "published_at": None,
                    "accessed_at": "2026-07-29",
                    "revision": None,
                    "match_level": "spec-only",
                    "supports": ["GPU memory"],
                }
            ],
            "plans": [
                valid_plan("economic", 1),
                valid_plan("peak_production", 2),
            ],
            "risks": [],
            "benchmark_plan": {
                "required": True,
                "matrix": [],
                "acceptance_criteria": [],
                "scale_out_triggers": [],
            },
        }

    def test_valid_output(self):
        self.assertEqual(validate_output.validate(self.payload()), [])

    def test_deployment_framework_is_required(self):
        payload = self.payload()
        payload["plans"][0].pop("deployment_framework")
        errors = validate_output.validate(payload)
        self.assertTrue(any("deployment_framework" in item for item in errors))

    def test_forbidden_cloud_field(self):
        payload = self.payload()
        payload["cloud_provider"] = "x"
        errors = validate_output.validate(payload)
        self.assertTrue(any("forbidden" in item for item in errors))

    def test_benchmark_required_has_null_performance(self):
        payload = self.payload()
        payload["plans"][0]["expected_performance"]["ttft_ms_p95"] = 100
        errors = validate_output.validate(payload)
        self.assertTrue(any("must be null" in item for item in errors))

    def test_rejects_unapproved_evidence_source_type(self):
        payload = self.payload()
        payload["evidence"][0]["source_type"] = "news_article"
        errors = validate_output.validate(payload)
        self.assertTrue(any("source_type is invalid" in item for item in errors))

    def test_rejects_benchmark_source_for_gpu_spec(self):
        payload = self.payload()
        payload["evidence"][0]["source_type"] = "reproducible_benchmark"
        errors = validate_output.validate(payload)
        self.assertTrue(any("is not allowed for gpu" in item for item in errors))



class AutomaticDeliveryTests(unittest.TestCase):
    def test_auto_selection_allows_missing_hardware_and_keeps_multi_card_options(self):
        request = platform_request()
        request.pop("hardware_profile")
        request["model"]["parameters_b"] = 80
        request["model"]["artifact_gb"] = 170
        result = calculate_request(request)
        self.assertEqual(result["selection_mode"], "auto_select")
        self.assertIsNone(result["tiers"]["economic"]["gpu_capacity"]["gpus_per_replica"])
        candidates = result["gpu_selection"]["economic"]
        self.assertTrue(candidates)
        self.assertTrue(any(item["quantity_per_replica"] > 1 for item in candidates))
        self.assertTrue(
            any(item["vram_gb"] < result["tiers"]["economic"]["memory"]["required_vram_per_replica_gb"] for item in candidates)
        )

    def test_verified_plan_renders_standalone_html(self):
        from model_private_skill.delivery import build_plan, render_html
        from model_private_skill.output_validation import validate

        request = platform_request()
        request.pop("hardware_profile")
        calculation = calculate_request(request)
        enrichment = {
            "evidence": [
                {
                    "id": "E-model", "category": "model", "publisher": "Example Publisher",
                    "source_type": "official_artifact", "title": "Model config",
                    "url": "https://example.invalid/model", "published_at": None,
                    "accessed_at": "2026-09-14", "revision": "abc123",
                    "match_level": "exact", "supports": ["model structure"],
                },
                {
                    "id": "E-engine", "category": "engine", "publisher": "Example Engine",
                    "source_type": "official_documentation", "title": "Engine docs",
                    "url": "https://example.invalid/engine", "published_at": None,
                    "accessed_at": "2026-09-14", "revision": "1.0",
                    "match_level": "similar", "supports": ["framework compatibility"],
                },
            ],
            "framework": {
                "name": "Example Engine", "version_or_commit": "1.0",
                "reason": "Verified by supplied engine evidence.",
                "required_features": ["continuous batching"], "evidence_ids": ["E-engine"],
            },
        }
        plan = build_plan(calculation, enrichment)
        self.assertEqual(validate(plan), [])
        html = render_html(plan)
        self.assertIn("<!doctype html>", html)
        self.assertIn("资源配置", html)
        self.assertIn("GPU 选型建议", html)
        self.assertNotIn("{{", html)
if __name__ == "__main__":
    unittest.main()
