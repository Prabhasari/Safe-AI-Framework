import subprocess
from typing import Tuple


class PlantUMLRenderer:
    """
    Simple wrapper around plantuml.jar.
    Uses `java -jar plantuml.jar -tsvg -pipe` to turn PlantUML text into SVG.
    """

    def __init__(self, jar_path: str):
        self.jar_path = jar_path

    def render_svg(self, plantuml_text: str) -> Tuple[str, str | None]:
        """
        Returns (svg_text, error_message).
        If error_message is not None, svg_text may be empty.
        """
        try:
            proc = subprocess.run(
                ["java", "-jar", self.jar_path, "-tsvg", "-pipe"],
                input=plantuml_text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,  # we'll inspect returncode ourselves
            )

            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", errors="ignore")
                return "", f"PlantUML error (code {proc.returncode}): {err}"

            svg = proc.stdout.decode("utf-8", errors="ignore")
            return svg, None

        except FileNotFoundError:
            return "", "Java or plantuml.jar not found. Check JAVA installation and jar path."
        except Exception as e:
            return "", f"Unexpected error running PlantUML: {e}"
