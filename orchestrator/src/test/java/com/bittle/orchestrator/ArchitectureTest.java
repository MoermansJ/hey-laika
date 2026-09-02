package com.bittle.orchestrator;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.domain.JavaMethod;
import com.tngtech.archunit.core.domain.JavaModifier;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.ArchCondition;
import com.tngtech.archunit.lang.ConditionEvents;
import com.tngtech.archunit.lang.SimpleConditionEvent;
import java.util.List;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

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
    void givenUseCaseClasses_whenShapeChecked_thenEachIsConcreteWithExactlyOnePublicExecuteMethod() {
        classes()
                .that().resideInAPackage("..application.usecase..")
                .should().haveSimpleNameEndingWith("UseCase")
                .andShould().beTopLevelClasses()
                .andShould().notBeInterfaces()
                .andShould(haveExactlyOnePublicMethodNamed("execute"))
                .check(productionClasses);
    }

    @Test
    void givenInboundAdapters_whenDependenciesChecked_thenTheyCallUseCasesNotServices() {
        noClasses()
                .that().resideInAPackage("..adapter.in..")
                .should().dependOnClassesThat().resideInAPackage("..application.service..")
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

    private static ArchCondition<JavaClass> haveExactlyOnePublicMethodNamed(String name) {
        return new ArchCondition<>("have exactly one public method, named " + name) {
            @Override
            public void check(JavaClass clazz, ConditionEvents events) {
                var publicMethods = clazz.getMethods().stream()
                        .filter(method -> method.getModifiers().contains(JavaModifier.PUBLIC))
                        .map(JavaMethod::getName)
                        .toList();
                events.add(new SimpleConditionEvent(clazz, publicMethods.equals(List.of(name)),
                        clazz.getSimpleName() + " has public methods " + publicMethods));
            }
        };
    }
}
