import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

import requests

from swagger_coverage_py.configs import API_DOCS_FORMAT, DEBUG_MODE
from swagger_coverage_py.docs_writers.api_doc_writer import write_api_doc_to_file


class CoverageReporter:
    def __init__(self, api_name: str, host: str, verify: bool = True):
        self.host = host
        self.verify = verify
        self.swagger_doc_file = f"swagger-doc-{api_name}.{API_DOCS_FORMAT}"
        self.output_dir = self.__get_output_dir()
        self.swagger_coverage_config = f"swagger-coverage-config-{api_name}.json"
        self.ignored_paths = self.__get_ignored_paths_from_config()

    def __get_output_dir(self):
        output_dir = "swagger-coverage-output"
        subdir = re.match(r"(^\w*)://(.*)", self.host).group(2).replace(".", "_").replace(":", "_")
        return f"{output_dir}/{subdir}"

    def __get_ignored_paths_from_config(self) -> List[str]:
        """Reads the swagger-coverage-config-<api_name>.json file and returns
        a list of endpoints/paths to exclude from the report

        """
        paths_to_ignore = []
        if not self.swagger_coverage_config:
            return paths_to_ignore

        with open(self.swagger_coverage_config, "r") as file:
            data = json.load(file)
            paths = data.get("rules").get("paths", {})
            if paths.get("enable", False):
                paths_to_ignore = paths.get("ignore")

        return paths_to_ignore

    def setup(
        self, path_to_swagger_json: str, auth: object = None, cookies: dict = None
    ):
        """Setup all required attributes to generate report

        :param path_to_swagger_json: The relative URL path to the swagger.json (example: "/docs/api")
        :param auth: Authentication object acceptable by "requests" library
        :param cookies: Cookies dictionary. (Usage example: set this to bypass Okta auth locally)

        """
        link_to_swagger_json = f"{self.host}{path_to_swagger_json}"

        response = requests.get(
            link_to_swagger_json, auth=auth, cookies=cookies, verify=self.verify
        )
        assert response.ok, (
            f"Swagger doc is not pulled. See details: "
            f"{response.status_code} {response.request.url}"
            f"{response.content}\n{response.content}"
        )
        if self.swagger_coverage_config:
            write_api_doc_to_file(
                self.swagger_doc_file,
                api_doc_data=response,
                paths_to_delete=self.ignored_paths,
            )

    import platform
    import subprocess
    import os
    from pathlib import Path
    import logging

    logger = logging.getLogger(__name__)

    def _generate_report_windows(
            self,
            command
            ):
        """Запуск генерации отчета на Windows через classpath"""
        base_dir = os.path.join(os.path.dirname(__file__), "swagger-coverage-commandline")
        lib_path = os.path.join(base_dir, "lib", "*")

        # Формируем classpath для Java
        classpath = lib_path.replace("/", os.sep)
        java_command = [
            "java",
            "-cp", classpath,
            "com.github.viclovsky.swagger.coverage.CommandLine",
            "-s", self.swagger_doc_file,
            "-i", self.output_dir,
        ]
        if self.swagger_coverage_config:
            java_command.extend(["-c", self.swagger_coverage_config])

        # Запускаем с обработкой ошибок
        try:
            if not DEBUG_MODE:
                result = subprocess.run(
                    java_command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
            else:
                result = subprocess.run(java_command, check=True)
            logger.debug("Windows report generation completed successfully")
            return result
        except subprocess.CalledProcessError as e:
            error_msg = (
                f"Swagger-coverage failed on Windows.\n"
                f"Command: {' '.join(e.cmd)}\n"
                f"Exit code: {e.returncode}"
            )
            if DEBUG_MODE:
                error_msg += f"\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
            raise RuntimeError(error_msg) from e
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Java not found. Make sure Java is installed and in PATH.\n"
                f"Tried to execute: {' '.join(java_command)}"
            ) from e

    def generate_report(
            self
            ):
        """Генерация отчета swagger-coverage"""
        # Создаем выходную директорию
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        # Для Windows используем специальный метод через Java classpath
        if platform.system() == "Windows":
            return self._generate_report_windows()

        # Для Unix систем используем прямой вызов бинарника
        inner_location = os.path.join(
            "swagger-coverage-commandline",
            "bin",
            "swagger-coverage-commandline"
        )
        cmd_path = os.path.join(os.path.dirname(__file__), inner_location)

        # Проверяем существование бинарника
        if not Path(cmd_path).exists():
            raise FileNotFoundError(
                f"Commandline tools not found at:\n{cmd_path}\n"
                "Make sure swagger-coverage-commandline is properly installed."
            )

        # Формируем команду
        command = [cmd_path, "-s", self.swagger_doc_file, "-i", self.output_dir]
        if self.swagger_coverage_config:
            command.extend(["-c", self.swagger_coverage_config])

        # Запускаем с обработкой ошибок
        try:
            if not DEBUG_MODE:
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )
            else:
                result = subprocess.run(command, check=True)

            logger.debug(f"Report generated successfully: {self.output_dir}")
            return result

        except subprocess.CalledProcessError as e:
            error_msg = (
                f"swagger-coverage CommandLine failed.\n"
                f"Command: {' '.join(e.cmd)}\n"
                f"Exit code: {e.returncode}\n"
            )
            if hasattr(e, 'stdout') and e.stdout:
                error_msg += f"STDOUT:\n{e.stdout}\n"
            if hasattr(e, 'stderr') and e.stderr:
                error_msg += f"STDERR:\n{e.stderr}"
            raise RuntimeError(error_msg) from e
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Swagger-coverage binary not found or not executable:\n{cmd_path}\n"
                "Check if file exists and has execute permissions."
            ) from e


    def cleanup_input_files(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
