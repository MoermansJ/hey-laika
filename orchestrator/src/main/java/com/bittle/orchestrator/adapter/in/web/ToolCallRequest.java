package com.bittle.orchestrator.adapter.in.web;

/**
 * Body of POST /api/v1/agent/{robotId}/submit-tool (AGENT-15).
 *
 * @param toolName   named behavior to run (one of GET .../tools)
 * @param goal       goal the call should achieve; outcome evaluation and learning use it
 * @param decisionId UUID shared by every tool call of one agent decision; optional
 */
public record ToolCallRequest(String toolName, String goal, String decisionId) {
}
