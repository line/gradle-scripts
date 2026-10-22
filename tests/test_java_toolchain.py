"""Run with: python3 -m unittest discover -s tests -v

Requires Gradle 8.14+ on PATH, or set GRADLE to select its executable.
"""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]


class JavaToolchainTest(unittest.TestCase):
    def assert_toolchain_vendor(self, subject_flags, requires_azul):
        with tempfile.TemporaryDirectory(prefix="java-toolchain-test-") as directory:
            root = Path(directory)
            (root / "gradle").mkdir()
            (root / "gradle/scripts").symlink_to(SCRIPTS_DIR, target_is_directory=True)
            (root / "dependencies.toml").write_text("", encoding="utf-8")

            projects = {
                "plain": ["java"],
                "shaded": ["java", "shade"],
                "nested:subject": subject_flags,
            }
            settings = [
                "rootProject.name = 'java-toolchain-test'",
                'apply from: "$rootDir/gradle/scripts/settings-flags.gradle"',
            ]
            for name, flags in projects.items():
                (root / name.replace(":", "/")).mkdir(parents=True)
                settings.append(f"includeWithFlags ':{name}', " + ", ".join(map(repr, flags)))
            (root / "settings.gradle").write_text("\n".join(settings), encoding="utf-8")

            (root / "build.gradle").write_text(
                """
allprojects {
    ext.artifactId = name
    ext.automaticModuleName = null
}

apply from: "$rootDir/gradle/scripts/lib/java.gradle"

tasks.register('verifyToolchains') {
    doLast {
        def requiresAzul = providers.gradleProperty('requiresAzul').get().toBoolean()
        def javaProjects = projectsWithFlags('java')
        assert javaProjects*.path.containsAll([':plain', ':shaded'])
        javaProjects.each { p ->
            def toolchain = p.extensions.getByType(JavaPluginExtension).toolchain
            def vendor = toolchain.vendor.get()
            assert vendor.matches('Azul Systems, Inc.'): "${p.path}: ${vendor}"
            assert vendor.matches('Eclipse Adoptium') == !requiresAzul: "${p.path}: ${vendor}"
            assert toolchain.languageVersion.get() == JavaLanguageVersion.of(17)
            assert toolchain.implementation.get() == JvmImplementation.VENDOR_SPECIFIC
        }
    }
}
""",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    os.environ.get("GRADLE", "gradle"),
                    "--project-dir", str(root), "--console=plain", "--quiet",
                    "-PbuildJdkVersion=17", f"-PrequiresAzul={str(requires_azul).lower()}",
                    "verifyToolchains",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_plain_java_does_not_require_azul(self):
        self.assert_toolchain_vendor(["java"], False)

    def test_shade_without_trim_does_not_require_azul(self):
        self.assert_toolchain_vendor(["java", "shade"], False)

    def test_relocate_without_trim_does_not_require_azul(self):
        self.assert_toolchain_vendor(["java", "relocate"], False)

    def test_nested_trim_requires_azul_for_every_java_project(self):
        self.assert_toolchain_vendor(["java", "trim"], True)

    def test_non_java_trim_does_not_require_azul(self):
        self.assert_toolchain_vendor(["trim"], False)
