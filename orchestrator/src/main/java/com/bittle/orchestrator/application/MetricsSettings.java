package com.bittle.orchestrator.application;

/**
 * AI cost valuation: adapters measure exact token counts; the orchestrator
 * alone knows prices. USD per million tokens.
 */
public record MetricsSettings(double claudeInputUsdPerMtok, double claudeOutputUsdPerMtok) {
}
