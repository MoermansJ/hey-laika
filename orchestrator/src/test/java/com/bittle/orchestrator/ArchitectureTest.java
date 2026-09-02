package com.bittle.orchestrator;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * Clean-architecture rules: infrastructure → adapter → application → domain.
 * The core (domain + application) is framework-free; adapters never talk to
 * each other directly. Any violation fails the build.
 *
 * <p>Deliberately plain JUnit Jupiter with {@code ArchRule.check} rather than
 * the ArchUnit JUnit 5 engine: under this project's Surefire/JUnit Platform
 * combination the engine discovered zero tests and silently passed a
 * known-bad rule, so it cannot be trusted to guard the build.
 */
class ArchitectureTest {

    private static JavaClasses productionClasses;

    @BeforeAll
    static void importProductionClasses() {
        productionClasses = new ClassFileImporter()
                .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
                .importPackages("com.bittle.orchestrator");
    }

    @Test
    void givenProductionClasses_whenLayersChecked_thenDependenciesOnlyPointInward() {
        layeredArchitecture()
                .consideringOnlyDependenciesInLayers()
                .layer("Domain").definedBy("..domain..")
                .layer("Application").definedBy("..application..")
                .layer("Adapter").definedBy("..adapter..")
                .layer("Infrastructure").definedBy("..infrastructure..")
                .whereLayer("Infrastructure").mayNotBeAccessedByAnyLayer()
                .whereLayer("Adapter").mayOnlyBeAccessedByLayers("Infrastructure")
                .whereLayer("Application").mayOnlyBeAccessedByLayers("Adapter", "Infrastructure")
                .whereLayer("Domain").mayOnlyBeAccessedByLayers("Application", "Adapter",
                        "Infrastructure")
                .check(productionClasses);
    }

    @Test
    void givenDomainClasses_whenDependenciesChecked_thenOnlyJavaAndDomainAreUsed() {
        classes()
                .that().resideInAPackage("..domain..")
                .should().onlyDependOnClassesThat().resideInAnyPackage("java..", "..domain..")
                .check(productionClasses);
    }

    @Test
    void givenApplicationClasses_whenDependenciesChecked_thenNoFrameworkIsUsed() {
        classes()
                .that().resideInAPackage("..application..")
                .should().onlyDependOnClassesThat()
                .resideInAnyPackage("java..", "org.slf4j..", "..domain..", "..application..")
                .check(productionClasses);
    }

    @Test
    void givenAdapterPackages_whenDependenciesChecked_thenAdaptersDoNotDependOnEachOther() {
        slices()
                .matching("..adapter.(*).(*)..")
                .should().notDependOnEachOther()
                .check(productionClasses);
    }

    @Test
    void givenClassesOutsideInfrastructure_whenDependenciesChecked_thenNoneReachInfrastructure() {
        noClasses()
                .that().resideOutsideOfPackage("..infrastructure..")
                .should().dependOnClassesThat().resideInAPackage("..infrastructure..")
                .check(productionClasses);
    }
}
