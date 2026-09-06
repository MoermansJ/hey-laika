package com.bittle.orchestrator.infrastructure.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.tags.Tag;
import java.util.Comparator;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    private static final String DESCRIPTION = """
            Fleet orchestrator for the Bittle robot dog. Routes under /api/robots/{robotId} \
            address one robot; most of them relay to the same path on that robot's Python \
            adapter, so their bodies are the adapter's JSON and are typed as plain objects.

            Errors use the envelope {"error": code, "message": text}: 404 robot_not_found, \
            400 bad_request, 409 behavior_loop_running or behavior_loop_held_elsewhere, and \
            502 adapter_unavailable when the adapter cannot be reached. Error responses from \
            the adapter itself are forwarded verbatim with their status.

            Operations marked deprecated belong to the adapter's old brain and are scheduled \
            for removal.""";

    @Bean
    OpenAPI orchestratorOpenApi() {
        return new OpenAPI().info(new Info()
                .title("Bittle orchestrator API")
                .version("v1")
                .description(DESCRIPTION));
    }

    @Bean
    OpenApiCustomizer sortedTags() {
        return openApi -> {
            if (openApi.getTags() != null) {
                openApi.getTags().sort(Comparator.comparing(Tag::getName));
            }
        };
    }
}
