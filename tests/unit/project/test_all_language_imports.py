"""Tests for import extraction across all supported languages."""

from pathlib import Path

import pytest

from interpreter.project.imports import extract_imports
from interpreter.project.types import ImportRef
from interpreter.constants import Language


class TestJavaScriptImportExtraction:
    def test_esm_named_import(self):
        source = b'import { foo } from "./utils";\n'
        refs = extract_imports(source, Path("main.js"), Language.JAVASCRIPT)
        assert len(refs) == 1
        assert refs[0].module_path == "./utils"
        assert "foo" in refs[0].names
        assert refs[0].is_relative is True

    def test_esm_default_import(self):
        source = b'import React from "react";\n'
        refs = extract_imports(source, Path("main.js"), Language.JAVASCRIPT)
        assert len(refs) == 1
        assert refs[0].module_path == "react"
        assert refs[0].is_system is True

    def test_cjs_require(self):
        source = b'const bar = require("./bar");\n'
        refs = extract_imports(source, Path("main.js"), Language.JAVASCRIPT)
        assert len(refs) == 1
        assert refs[0].module_path == "./bar"
        assert refs[0].kind == "require"
        assert refs[0].is_relative is True

    def test_system_package(self):
        source = b'import express from "express";\n'
        refs = extract_imports(source, Path("main.js"), Language.JAVASCRIPT)
        assert len(refs) == 1
        assert refs[0].is_system is True


class TestTypeScriptImportExtraction:
    def test_typescript_shares_js_extraction(self):
        source = b'import { Component } from "./component";\n'
        refs = extract_imports(source, Path("app.ts"), Language.TYPESCRIPT)
        assert len(refs) == 1
        assert refs[0].module_path == "./component"
        assert refs[0].is_relative is True


class TestJavaImportExtraction:
    def test_simple_import(self):
        source = b"import com.example.Utils;\n"
        refs = extract_imports(source, Path("Main.java"), Language.JAVA)
        assert len(refs) == 1
        assert refs[0].names == ("Utils",)
        assert refs[0].module_path == "com.example"

    def test_static_import(self):
        source = b"import static com.example.Math.add;\n"
        refs = extract_imports(source, Path("Main.java"), Language.JAVA)
        assert len(refs) == 1
        assert refs[0].names == ("add",)

    def test_system_import(self):
        source = b"import java.util.List;\n"
        refs = extract_imports(source, Path("Main.java"), Language.JAVA)
        assert len(refs) == 1
        assert refs[0].is_system is True

    def test_wildcard_import(self):
        source = b"import com.example.*;\n"
        refs = extract_imports(source, Path("Main.java"), Language.JAVA)
        assert len(refs) == 1
        assert refs[0].names == ("*",)


class TestGoImportExtraction:
    def test_single_import(self):
        source = b'import "fmt"\n'
        refs = extract_imports(source, Path("main.go"), Language.GO)
        assert len(refs) == 1
        assert refs[0].module_path == "fmt"
        assert refs[0].is_system is True

    def test_grouped_imports(self):
        source = b'import (\n  "fmt"\n  "os/exec"\n)\n'
        refs = extract_imports(source, Path("main.go"), Language.GO)
        assert len(refs) == 2
        modules = {r.module_path for r in refs}
        assert "fmt" in modules
        assert "os/exec" in modules


class TestRustImportExtraction:
    def test_use_crate(self):
        source = b"use crate::utils;\n"
        refs = extract_imports(source, Path("main.rs"), Language.RUST)
        assert len(refs) == 1
        assert refs[0].kind == "use"
        assert refs[0].is_relative is True
        assert "utils" in refs[0].names

    def test_use_std(self):
        source = b"use std::collections::HashMap;\n"
        refs = extract_imports(source, Path("main.rs"), Language.RUST)
        assert len(refs) == 1
        assert refs[0].is_system is True

    def test_mod_declaration(self):
        source = b"mod helpers;\n"
        refs = extract_imports(source, Path("main.rs"), Language.RUST)
        assert len(refs) == 1
        assert refs[0].kind == "mod"
        assert refs[0].module_path == "helpers"

    def test_use_list(self):
        source = b"use std::collections::{HashMap, HashSet};\n"
        refs = extract_imports(source, Path("main.rs"), Language.RUST)
        assert len(refs) == 1
        assert set(refs[0].names) == {"HashMap", "HashSet"}


class TestCImportExtraction:
    def test_local_include(self):
        source = b'#include "header.h"\n'
        refs = extract_imports(source, Path("main.c"), Language.C)
        assert len(refs) == 1
        assert refs[0].module_path == "header.h"
        assert refs[0].kind == "include"
        assert refs[0].is_system is False

    def test_system_include(self):
        source = b"#include <stdio.h>\n"
        refs = extract_imports(source, Path("main.c"), Language.C)
        assert len(refs) == 1
        assert refs[0].is_system is True

    def test_cpp_same_as_c(self):
        source = b'#include "mylib.h"\n#include <iostream>\n'
        refs = extract_imports(source, Path("main.cpp"), Language.CPP)
        assert len(refs) == 2
        local = [r for r in refs if not r.is_system]
        system = [r for r in refs if r.is_system]
        assert len(local) == 1
        assert len(system) == 1


class TestCSharpImportExtraction:
    def test_using_directive(self):
        source = b"using System;\n"
        refs = extract_imports(source, Path("Program.cs"), Language.CSHARP)
        assert len(refs) == 1
        assert refs[0].kind == "using"
        assert refs[0].is_system is True

    def test_using_local(self):
        source = b"using MyProject.Models;\n"
        refs = extract_imports(source, Path("Program.cs"), Language.CSHARP)
        assert len(refs) == 1
        assert refs[0].is_system is False

    def test_using_alias(self):
        source = b"using MyAlias = System.Text;\n"
        refs = extract_imports(source, Path("Program.cs"), Language.CSHARP)
        assert len(refs) == 1
        assert refs[0].alias == "MyAlias"


class TestKotlinImportExtraction:
    def test_simple_import(self):
        source = b"import com.example.Utils\n"
        refs = extract_imports(source, Path("Main.kt"), Language.KOTLIN)
        assert len(refs) == 1
        assert refs[0].names == ("Utils",)

    def test_system_import(self):
        source = b"import kotlin.collections.Map\n"
        refs = extract_imports(source, Path("Main.kt"), Language.KOTLIN)
        assert len(refs) == 1
        assert refs[0].is_system is True


class TestScalaImportExtraction:
    def test_simple_import(self):
        source = b"import scala.io._\n"
        refs = extract_imports(source, Path("Main.scala"), Language.SCALA)
        assert len(refs) == 1
        assert refs[0].names == ("*",)
        assert refs[0].is_system is True

    def test_grouped_import(self):
        source = b"import scala.collection.mutable.{Map, Set}\n"
        refs = extract_imports(source, Path("Main.scala"), Language.SCALA)
        assert len(refs) == 1
        assert set(refs[0].names) == {"Map", "Set"}


class TestRubyImportExtraction:
    def test_require(self):
        source = b'require "utils"\n'
        refs = extract_imports(source, Path("main.rb"), Language.RUBY)
        assert len(refs) == 1
        assert refs[0].module_path == "utils"
        assert refs[0].kind == "require"

    def test_require_relative(self):
        source = b'require_relative "./helpers"\n'
        refs = extract_imports(source, Path("main.rb"), Language.RUBY)
        assert len(refs) == 1
        assert refs[0].is_relative is True


class TestPhpImportExtraction:
    def test_use_declaration(self):
        source = b"<?php\nuse App\\Models\\User;\n"
        refs = extract_imports(source, Path("index.php"), Language.PHP)
        assert len(refs) == 1
        assert refs[0].kind == "use"

    def test_require_once(self):
        source = b'<?php\nrequire_once "helpers.php";\n'
        refs = extract_imports(source, Path("index.php"), Language.PHP)
        assert len(refs) == 1
        assert refs[0].module_path == "helpers.php"


class TestLuaImportExtraction:
    def test_require_with_parens(self):
        source = b'local utils = require("utils")\n'
        refs = extract_imports(source, Path("main.lua"), Language.LUA)
        assert len(refs) == 1
        assert refs[0].module_path == "utils"
        assert refs[0].kind == "require"

    def test_require_without_parens(self):
        source = b'require "helpers"\n'
        refs = extract_imports(source, Path("main.lua"), Language.LUA)
        assert len(refs) == 1
        assert refs[0].module_path == "helpers"


class TestPascalImportExtraction:
    def test_uses_clause(self):
        source = b"uses SysUtils, Classes;\n"
        refs = extract_imports(source, Path("main.pas"), Language.PASCAL)
        assert len(refs) == 2
        modules = {r.module_path for r in refs}
        assert "SysUtils" in modules
        assert "Classes" in modules

    def test_system_unit(self):
        source = b"uses SysUtils;\n"
        refs = extract_imports(source, Path("main.pas"), Language.PASCAL)
        assert len(refs) == 1
        assert refs[0].is_system is True
