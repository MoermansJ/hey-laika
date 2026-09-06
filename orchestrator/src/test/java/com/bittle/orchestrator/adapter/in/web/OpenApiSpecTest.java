package com.bittle.orchestrator.adapter.in.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.infrastructure.config.OpenApiConfig;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springdoc.core.configuration.SpringDocConfiguration;
import org.springdoc.core.configuration.SpringDocSpecPropertiesConfiguration;
import org.springdoc.core.properties.SpringDocConfigProperties;
import org.springdoc.webmvc.core.configuration.MultipleOpenApiSupportConfiguration;
import org.springdoc.webmvc.core.configuration.SpringDocWebMvcConfiguration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.context.annotation.Import;
import org.springframework.core.type.filter.RegexPatternTypeFilter;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.util.ClassUtils;

@WebMvcTest
@ImportAutoConfiguration({SpringDocConfiguration.class, SpringDocConfigProperties.class,
        SpringDocSpecPropertiesConfiguration.class, SpringDocWebMvcConfiguration.class,
        MultipleOpenApiSupportConfiguration.class})
@Import({OpenApiConfig.class, OpenApiSpecTest.UseCaseMocks.class})
@MockitoBean(types = OrchestratorMetricsPort.class)
class OpenApiSpecTest {

    private static final Path SPEC = Path.of("docs", "api", "openapi.json");

    @Autowired
    private MockMvcTester mvc;

    @Test
    void givenControllers_whenSpecGenerated_thenCommittedSpecIsCurrent() throws IOException {
        var result = mvc.get().uri("/v3/api-docs").exchange();
        assertThat(result).hasStatusOk();

        String generated = normalize(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
        String committed = Files.exists(SPEC) ? normalize(Files.readString(SPEC)) : "";
        Files.createDirectories(SPEC.getParent());
        Files.writeString(SPEC, generated);

        assertThat(generated.equals(committed))
                .as("%s was regenerated from the controllers and differs from the committed copy;"
                        + " review the diff and commit it", SPEC)
                .isTrue();
    }

    private static String normalize(String json) {
        String unix = json.replace("\r\n", "\n").strip();
        return unix + "\n";
    }

    @TestConfiguration
    static class UseCaseMocks {

        @Bean
        static BeanDefinitionRegistryPostProcessor useCaseMockRegistrar() {
            return (BeanDefinitionRegistry registry) -> {
                var scanner = new ClassPathScanningCandidateComponentProvider(false);
                scanner.addIncludeFilter(new RegexPatternTypeFilter(Pattern.compile(".*UseCase")));
                scanner.findCandidateComponents("com.bittle.orchestrator.application.usecase")
                        .forEach(definition -> {
                            Class<?> type = ClassUtils.resolveClassName(
                                    definition.getBeanClassName(), null);
                            registry.registerBeanDefinition(type.getSimpleName(), mockOf(type));
                        });
            };
        }

        private static <T> BeanDefinition mockOf(Class<T> type) {
            return BeanDefinitionBuilder.genericBeanDefinition(type, () -> Mockito.mock(type))
                    .getBeanDefinition();
        }
    }
}
