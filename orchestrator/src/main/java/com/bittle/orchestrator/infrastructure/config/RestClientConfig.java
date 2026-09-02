package com.bittle.orchestrator.infrastructure.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfig {

    @Bean
    public RestClient pythonRestClient() {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(3_000);
        // Choreography with real hardware sleeps through frame durations, so
        // reads can legitimately take a while.
        factory.setReadTimeout(30_000);
        return RestClient.builder().requestFactory(factory).build();
    }
}
