#!/usr/bin/env python3
"""
ComfyUI Remote Workflow Runner routes and helpers.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from flask import jsonify, render_template, request as flask_request


PLACEHOLDER_INPUT = "{input}"
PLACEHOLDER_IMAGE = "{image}"


@dataclass
class Placeholder:
    node_id: str
    field_path: str
    type: str
    node_title: str

    def to_dict(self) -> dict[str, str]:
        return {
            "nodeId": self.node_id,
            "fieldPath": self.field_path,
            "type": self.type,
            "nodeTitle": self.node_title,
        }


def normalize_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("Base URL 不能为空")
    if not value.startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    return value


def deep_clone_json(value: Any) -> Any:
    return copy.deepcopy(value)


def is_editor_workflow(workflow: Any) -> bool:
    return isinstance(workflow, dict) and isinstance(workflow.get("nodes"), list)


def is_non_executable_editor_node(node: dict[str, Any]) -> bool:
    class_type = str(node.get("type") or "").strip().lower()
    node_title = str(node.get("title") or "").strip().lower()
    node_name = str(node.get("properties", {}).get("Node name for S&R") or "").strip().lower()
    searchable = " ".join(part for part in [class_type, node_title, node_name] if part)

    known_annotation_types = {
        "label (rgthree)",
        "note",
        "sticky note",
    }
    if class_type in known_annotation_types:
        return True

    # rgthree label nodes are annotation-only and do not participate in execution.
    if "label" in searchable and "rgthree" in searchable:
        return True

    return False


def convert_editor_workflow_to_prompt(workflow: dict[str, Any]) -> dict[str, Any]:
    link_map: dict[int, list[Any]] = {}
    for link in workflow.get("links", []):
        if isinstance(link, list) and len(link) >= 4:
            link_id = int(link[0])
            origin_node_id = str(link[1])
            origin_slot = int(link[2])
            link_map[link_id] = [origin_node_id, origin_slot]

    prompt: dict[str, Any] = {}
    for node in workflow.get("nodes", []):
        if is_non_executable_editor_node(node):
            continue

        node_id = str(node.get("id"))
        prompt_node = {
            "class_type": node.get("type"),
            "inputs": {},
        }

        widget_values = list(node.get("widgets_values", []))
        widget_index = 0
        widget_inputs = [item for item in node.get("inputs", []) if item.get("widget")]
        consumed_widget_inputs = 0

        for input_item in node.get("inputs", []):
            input_name = input_item.get("name")
            if not input_name:
                continue

            link_id = input_item.get("link")
            if link_id is not None:
                linked_value = link_map.get(int(link_id))
                if linked_value is not None:
                    prompt_node["inputs"][input_name] = linked_value
                continue

            widget_meta = input_item.get("widget")
            if widget_meta and widget_index < len(widget_values):
                widget_value = widget_values[widget_index]
                prompt_node["inputs"][input_name] = widget_value
                widget_index += 1
                consumed_widget_inputs += 1

                # ComfyUI editor workflows sometimes store an extra seed behavior
                # token right after the numeric seed value.
                remaining_widget_values = len(widget_values) - widget_index
                remaining_widget_inputs = len(widget_inputs) - consumed_widget_inputs
                if (
                    input_name == "seed"
                    and remaining_widget_values > remaining_widget_inputs
                    and widget_index < len(widget_values)
                    and str(widget_values[widget_index]) in {"fixed", "randomize", "increment", "decrement"}
                ):
                    widget_index += 1

        prompt[node_id] = prompt_node

    return prompt


def build_node_title_map(workflow: Any, raw_workflow: dict[str, Any] | None = None) -> dict[str, str]:
    title_map: dict[str, str] = {}

    if isinstance(raw_workflow, dict) and isinstance(raw_workflow.get("nodes"), list):
        for node in raw_workflow.get("nodes", []):
            node_id = str(node.get("id"))
            title = (
                node.get("title")
                or node.get("properties", {}).get("Node name for S&R")
                or node.get("type")
                or node_id
            )
            title_map[node_id] = str(title)

    if isinstance(workflow, dict):
        for node_id, node_value in workflow.items():
            if node_id in title_map:
                continue
            if isinstance(node_value, dict):
                title = node_value.get("title") or node_value.get("class_type") or node_id
                title_map[str(node_id)] = str(title)

    return title_map


def parse_placeholders(workflow: Any, node_titles: dict[str, str] | None = None) -> list[dict[str, str]]:
    placeholders: list[Placeholder] = []
    titles = node_titles or {}

    def walk(current: Any, node_id: str | None = None, path: list[str] | None = None) -> None:
        current_path = path or []
        if isinstance(current, dict):
            next_node_id = node_id
            if not current_path and node_id is None:
                for key, value in current.items():
                    walk(value, node_id=str(key), path=[])
                return

            for key, value in current.items():
                walk(value, node_id=next_node_id, path=current_path + [str(key)])
            return

        if isinstance(current, list):
            for index, value in enumerate(current):
                walk(value, node_id=node_id, path=current_path + [str(index)])
            return

        if current == PLACEHOLDER_INPUT:
            placeholders.append(
                Placeholder(
                    node_id=node_id or "unknown",
                    field_path=".".join(current_path),
                    type="input",
                    node_title=titles.get(node_id or "unknown", node_id or "unknown"),
                )
            )
        elif current == PLACEHOLDER_IMAGE:
            placeholders.append(
                Placeholder(
                    node_id=node_id or "unknown",
                    field_path=".".join(current_path),
                    type="image",
                    node_title=titles.get(node_id or "unknown", node_id or "unknown"),
                )
            )

    walk(workflow)
    return [item.to_dict() for item in placeholders]


def read_path(mapping: dict[str, Any], field_path: str) -> Any:
    current: Any = mapping
    for segment in field_path.split("."):
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current


def write_path(mapping: dict[str, Any], field_path: str, value: Any) -> None:
    segments = field_path.split(".")
    current: Any = mapping
    for segment in segments[:-1]:
        current = current[int(segment)] if isinstance(current, list) else current[segment]

    last_segment = int(segments[-1]) if isinstance(current, list) else segments[-1]
    current[last_segment] = value


def apply_params(workflow: dict[str, Any], form_state: dict[str, Any]) -> dict[str, Any]:
    cloned = deep_clone_json(workflow)
    placeholders = parse_placeholders(cloned)

    for item in placeholders:
        field_key = f"{item['nodeId']}::{item['fieldPath']}"
        replacement = form_state.get(field_key, "")
        current_value = read_path(cloned[item["nodeId"]], item["fieldPath"])

        if current_value == PLACEHOLDER_INPUT:
            write_path(cloned[item["nodeId"]], item["fieldPath"], replacement)
        elif current_value == PLACEHOLDER_IMAGE:
            image_value = str(replacement).strip()
            write_path(cloned[item["nodeId"]], item["fieldPath"], image_value)

    return cloned


def fetch_remote_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, method=method, data=data, headers=headers)

    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Remote request failed ({exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Remote request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Remote response is not valid JSON") from exc


def load_workflow(base_url: str, workflow_name: str) -> dict[str, Any]:
    raw_name = (workflow_name or "").strip()
    if not raw_name:
        raise ValueError("Workflow name 不能为空")

    if raw_name.startswith(("http://", "https://")):
        return fetch_remote_json(raw_name)

    normalized_base_url = normalize_base_url(base_url)
    relative_name = raw_name.lstrip("/")

    if relative_name.startswith("api/userdata/"):
        return fetch_remote_json(f"{normalized_base_url}/{relative_name}")

    if "%2f" in relative_name.lower() and "/" not in relative_name:
        normalized_relative_name = relative_name
        if relative_name.lower().startswith("workflow%2f"):
            normalized_relative_name = f"workflows%2F{relative_name[len('workflow%2F'):]}"
        encoded_path = normalized_relative_name if normalized_relative_name.endswith(".json") else f"{normalized_relative_name}.json"
        return fetch_remote_json(f"{normalized_base_url}/api/userdata/{encoded_path}")

    decoded_name = parse.unquote(relative_name)
    if decoded_name.startswith("workflow/"):
        decoded_name = f"workflows/{decoded_name[len('workflow/'):]}"
    if decoded_name.startswith("workflows/"):
        encoded_path = parse.quote(decoded_name, safe="/")
        if not encoded_path.endswith(".json"):
            encoded_path = f"{encoded_path}.json"
        return fetch_remote_json(f"{normalized_base_url}/api/userdata/{encoded_path}")

    safe_name = decoded_name.removesuffix(".json")
    encoded_name = parse.quote(safe_name, safe="")
    return fetch_remote_json(f"{normalized_base_url}/api/userdata/workflows/{encoded_name}.json")


def submit_prompt(base_url: str, workflow_json: dict[str, Any]) -> dict[str, Any]:
    return fetch_remote_json(
        f"{normalize_base_url(base_url)}/api/prompt",
        method="POST",
        payload={"prompt": workflow_json},
    )


def list_workflows(base_url: str) -> list[dict[str, Any]]:
    return fetch_remote_json(
        f"{normalize_base_url(base_url)}/api/userdata?dir=workflows&recurse=true&split=false&full_info=true"
    )


def get_history(base_url: str, prompt_id: str) -> dict[str, Any]:
    safe_prompt_id = parse.quote((prompt_id or "").strip(), safe="")
    if not safe_prompt_id:
        raise ValueError("prompt_id 不能为空")
    return fetch_remote_json(f"{normalize_base_url(base_url)}/api/history/{safe_prompt_id}")


def extract_result_assets(base_url: str, history_payload: dict[str, Any]) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    normalized_base_url = normalize_base_url(base_url)

    for prompt_data in history_payload.values():
        outputs = prompt_data.get("outputs", {})
        for node_id, node_output in outputs.items():
            for asset_type in ("images", "gifs", "videos"):
                for item in node_output.get(asset_type, []):
                    filename = item.get("filename", "")
                    if not filename:
                        continue
                    query = parse.urlencode(
                        {
                            "filename": filename,
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        }
                    )
                    media_kind = "video" if asset_type in {"gifs", "videos"} else "image"
                    assets.append(
                        {
                            "nodeId": str(node_id),
                            "kind": media_kind,
                            "filename": filename,
                            "url": f"{normalized_base_url}/view?{query}",
                        }
                    )

    return assets


def infer_job_status(history_payload: dict[str, Any], prompt_id: str, submitted_at: float | None) -> tuple[str, str]:
    prompt_data = history_payload.get(prompt_id)
    if not prompt_data:
        age_seconds = time.time() - submitted_at if submitted_at else 0
        if age_seconds < 2:
            return "queued", "Prompt 已提交，等待远端 ComfyUI 接收。"
        return "running", "远端 ComfyUI 正在执行 workflow。"

    status_info = prompt_data.get("status", {}) if isinstance(prompt_data, dict) else {}
    status_str = str(status_info.get("status_str", "")).lower()
    completed = bool(status_info.get("completed"))

    if status_str in {"error", "failed"}:
        return "failed", status_info.get("messages", ["Workflow 执行失败"])[0] if status_info.get("messages") else "Workflow 执行失败"
    if completed or status_str in {"success", "completed"}:
        return "success", "Workflow 执行完成。"
    return "running", "远端 ComfyUI 正在执行 workflow。"


def create_remote_runner_routes(app, logger, media_list_getter=None, app_config: dict[str, Any] | None = None):
    job_store: dict[str, dict[str, Any]] = {}

    @app.get("/remote-runner")
    def remote_runner_index():
        return render_template("remote_runner.html")

    @app.get("/api/remote-runner/config")
    def remote_runner_config():
        upload_dir = str((app_config or {}).get("upload_dir", "images")).strip() or "images"
        return jsonify(
            {
                "defaults": {
                    "baseUrl": "http://127.0.0.1:8188",
                    "workflowName": "",
                },
                "uploadDir": upload_dir,
            }
        )

    @app.get("/api/remote-runner/media")
    def remote_runner_media():
        if media_list_getter is None:
            return jsonify({"items": []})
        return jsonify({"items": media_list_getter("image")})

    @app.get("/api/remote-runner/workflows")
    def remote_runner_workflows():
        base_url = flask_request.args.get("baseUrl", "")
        try:
            workflows = list_workflows(base_url)
            return jsonify({"items": workflows})
        except Exception as exc:
            logger.exception("加载 workflow 列表失败")
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/remote-runner/workflows/load")
    def remote_runner_load_workflow():
        payload = flask_request.get_json(silent=True) or {}
        base_url = payload.get("baseUrl", "")
        workflow_name = payload.get("workflowName", "")

        try:
            workflow = load_workflow(base_url, workflow_name)
            prompt_workflow = convert_editor_workflow_to_prompt(workflow) if is_editor_workflow(workflow) else workflow
            node_titles = build_node_title_map(prompt_workflow, workflow if is_editor_workflow(workflow) else None)
            placeholders = parse_placeholders(prompt_workflow, node_titles=node_titles)
            return jsonify(
                {
                    "workflow": prompt_workflow,
                    "rawWorkflow": workflow,
                    "placeholders": placeholders,
                    "workflowName": workflow_name.strip().removesuffix(".json"),
                }
            )
        except Exception as exc:
            logger.exception("加载远端 workflow 失败")
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/remote-runner/prompts/submit")
    def remote_runner_submit_prompt():
        payload = flask_request.get_json(silent=True) or {}
        base_url = payload.get("baseUrl", "")
        template = payload.get("template")
        form_state = payload.get("formState", {})

        if not isinstance(template, dict):
            return jsonify({"error": "template 必须为 workflow JSON 对象"}), 400

        try:
            built_workflow = apply_params(template, form_state)
            submit_result = submit_prompt(base_url, built_workflow)
            prompt_id = submit_result.get("prompt_id")
            if not prompt_id:
                raise RuntimeError("远端 ComfyUI 未返回 prompt_id")

            job_store[prompt_id] = {
                "baseUrl": normalize_base_url(base_url),
                "submittedAt": time.time(),
                "workflow": built_workflow,
            }
            return jsonify(
                {
                    "promptId": prompt_id,
                    "workflow": built_workflow,
                    "status": "queued",
                    "submittedAt": job_store[prompt_id]["submittedAt"],
                }
            )
        except Exception as exc:
            logger.exception("提交远端 workflow 失败")
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/remote-runner/prompts/<prompt_id>/history")
    def remote_runner_prompt_history(prompt_id: str):
        base_url = flask_request.args.get("baseUrl", "")
        job_meta = job_store.get(prompt_id, {})
        effective_base_url = base_url or job_meta.get("baseUrl", "")

        try:
            history_payload = get_history(effective_base_url, prompt_id)
            status, message = infer_job_status(history_payload, prompt_id, job_meta.get("submittedAt"))
            assets = extract_result_assets(effective_base_url, history_payload)
            return jsonify(
                {
                    "promptId": prompt_id,
                    "status": status,
                    "message": message,
                    "history": history_payload,
                    "results": assets,
                }
            )
        except Exception as exc:
            logger.exception("查询远端 workflow 状态失败")
            return jsonify({"error": str(exc)}), 400
