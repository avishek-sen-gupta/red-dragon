"""Two-pass audit across all 15 deterministic frontends.

Architecture
------------
Pass 1 (Dispatch Comparison — Block-Reachability):
    Parses source, collects all AST node types, compares against
    _EXPR_DISPATCH / _STMT_DISPATCH / NOISE_TYPES / COMMENT_TYPES.
    Unhandled types are classified using **block-reachability analysis**:
    only nodes that are direct named children of block-iterated nodes
    are flagged as substantive gaps. All others are deep structural nodes
    consumed by their parent's lowerer and can never produce SYMBOLIC.

Pass 2 (Runtime SYMBOLIC):
    Lowers source through each frontend, scans IR for SYMBOLIC instructions
    with "unsupported:" operands.

How the Lowering Dispatch Chain Works
-------------------------------------
The fallback chain in BaseFrontend:

    lower(root)
      → _lower_block(root)           # iterates named children
        → _lower_stmt(child)         # skip noise/comments; try STMT_DISPATCH
          → _lower_expr(child)       # fallback: try EXPR_DISPATCH
            → SYMBOLIC("unsupported:X")  # final fallback for unknown types

A node type produces SYMBOLIC **only** if it is passed to _lower_stmt as a
direct named child of a block-iterated node. _lower_block iterates children
when:
  1. The root node is passed from lower()
  2. A node's type maps to _lower_block itself in _STMT_DISPATCH (e.g.,
     compound_statement in C, block in Rust, statement_block in JS)

Nodes that are only ever children of handled parents (like parameter_list
inside function_definition) are consumed by the parent's lowerer directly —
they never pass through _lower_block → _lower_stmt.

Why One-Level Parent Checking Produced False Positives
------------------------------------------------------
The old heuristic checked whether an unhandled node's immediate parent was
in a dispatch table. This failed when the parent was also unhandled but was
itself deep structural (never block-iterated). For example, a type_annotation
inside a typed_parameter inside a parameters inside a function_definition:
the old heuristic saw typed_parameter (unhandled parent) and flagged
type_annotation as substantive, even though typed_parameter itself is never
block-iterated.

Root Node Edge Case
-------------------
Root nodes (module, program, translation_unit, etc.) are always reachable
because lower() calls _lower_block(root) directly. They show up as
"substantive" but are harmless — they're the entry point, not a gap.
"""

from __future__ import annotations

import dataclasses
import logging

import tree_sitter_language_pack

from interpreter.frontends import get_deterministic_frontend
from interpreter.frontends._base import BaseFrontend
from interpreter.ir import Opcode

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Comprehensive source samples per language
# ---------------------------------------------------------------------------

SOURCES: dict[str, str] = {}

SOURCES["python"] = r"""
# === basic assignments ===
x = 1
y, z = 2, 3
a, *b = [1, 2, 3, 4]
(p, q) = (10, 20)

# === walrus operator ===
if (n := len("hello")) > 3:
    print(n)

# === match/case ===
match command:
    case "quit":
        pass
    case "go" if True:
        pass
    case ["drop", *objects]:
        pass
    case {"text": message}:
        print(message)
    case _:
        pass

# === type annotations ===
age: int = 25
name: str = "Alice"

# === augmented assignment ===
x += 1
x -= 1
x *= 2
x //= 3
x **= 2
x |= 0xFF
x &= 0x0F
x ^= 0x01
x >>= 2
x <<= 1

# === async for / async with ===
async def af():
    async for item in aiter:
        pass
    async with ctx as c:
        pass

# === try / except / else / finally ===
try:
    risky()
except ValueError as e:
    handle(e)
except (TypeError, KeyError):
    pass
else:
    ok()
finally:
    cleanup()

# === function def with decorators, defaults, *args, **kwargs ===
@decorator
def func(a, b=10, *args, **kwargs):
    return a + b

# === class def ===
class MyClass(Base):
    class_var = 42
    def method(self):
        return self.class_var

# === lambda ===
fn = lambda x, y: x + y

# === list/dict/set comprehensions ===
squares = [x**2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
d = {k: v for k, v in items}
s = {x for x in range(10)}

# === generator expression ===
gen = (x**2 for x in range(10))

# === conditional expression ===
val = "yes" if True else "no"

# === yield / yield from ===
def gen_func():
    yield 1
    yield from [2, 3]

# === starred ===
result = [*a, *b]
merged = {**d1, **d2}

# === assert ===
assert x > 0, "must be positive"

# === del ===
del x

# === global / nonlocal ===
def scope():
    global g
    nonlocal nl

# === with ===
with open("f") as f:
    data = f.read()

# === for ===
for i in range(10):
    if i == 5:
        break
    if i == 3:
        continue
    print(i)

# === while ===
while x > 0:
    x -= 1

# === raise ===
raise ValueError("oops")

# === import / from import ===
import os
from sys import argv
from pathlib import Path as P

# === string interpolation (f-string) ===
msg = f"Hello {name}!"

# === slice ===
sub = lst[1:3]
sub2 = lst[::2]

# === ellipsis ===
x = ...

# === type alias (3.12+) ===
type Vector = list[float]

# === pass ===
pass
"""

SOURCES["javascript"] = r"""
// === variable declarations ===
var a = 1;
let b = 2;
const c = 3;

// === destructuring ===
const [x, y, ...rest] = [1, 2, 3, 4];
const {name, age} = person;
const {a: aa, b: bb = 10} = obj;

// === arrow functions ===
const add = (a, b) => a + b;
const greet = (name) => {
    return `Hello ${name}`;
};

// === template literals ===
const msg = `Value is ${x + y}`;
const tagged = html`<div>${content}</div>`;

// === class with getter/setter ===
class Animal {
    #privateField = 0;
    constructor(name) { this.name = name; }
    get displayName() { return this.name; }
    set displayName(val) { this.name = val; }
    static create(name) { return new Animal(name); }
    speak() { return "..."; }
}

// === async/await ===
async function fetchData() {
    try {
        const resp = await fetch(url);
        const data = await resp.json();
        return data;
    } catch (e) {
        console.error(e);
    } finally {
        cleanup();
    }
}

// === generators ===
function* gen() {
    yield 1;
    yield* [2, 3];
}

// === for...of / for...in ===
for (const item of items) { process(item); }
for (const key in obj) { use(key); }

// === optional chaining / nullish coalescing ===
const val = obj?.prop?.nested ?? "default";

// === spread ===
const arr = [...a, ...b];
const merged = {...obj1, ...obj2};

// === ternary ===
const result = cond ? "yes" : "no";

// === comma expression ===
const z = (1, 2, 3);

// === switch ===
switch (action) {
    case "start": begin(); break;
    case "stop": end(); break;
    default: idle();
}

// === throw ===
throw new Error("fail");

// === typeof / instanceof / in / delete / void ===
typeof x;
x instanceof Array;
"key" in obj;
delete obj.prop;
void 0;

// === new ===
const d = new Date();

// === regex ===
const re = /abc/gi;

// === label statement ===
outer: for (let i = 0; i < 10; i++) {
    inner: for (let j = 0; j < 10; j++) {
        if (j === 5) break outer;
    }
}

// === do...while ===
do {
    x++;
} while (x < 10);

// === with statement (deprecated) ===
with (obj) { foo; }

// === comma expression ===
for (let i = 0, j = 10; i < j; i++, j--) {}

// === sequence expression ===
const seqResult = (a = 1, b = 2, a + b);

// === bitwise ===
const bits = a & b | c ^ d;
const shifted = a << 2 | b >>> 1;

// === logical assignment ===
a ||= b;
a &&= c;
a ??= d;

// === import/export ===
import {foo} from "mod";
export default function() {}
export { a, b };
"""

SOURCES["typescript"] = r"""
// === type annotations ===
let x: number = 42;
const name: string = "Alice";
let arr: number[] = [1, 2, 3];

// === interface ===
interface Shape {
    area(): number;
    perimeter?(): number;
}

// === type alias ===
type Point = { x: number; y: number };
type Result<T> = T | Error;

// === enum ===
enum Direction { Up, Down, Left, Right }
const enum Color { Red = 1, Green = 2, Blue = 3 }

// === generic function ===
function identity<T>(arg: T): T { return arg; }

// === class with access modifiers ===
class MyClass {
    private _value: number;
    public readonly name: string;
    protected id: number;
    constructor(name: string, val: number) {
        this.name = name;
        this._value = val;
    }
    get value(): number { return this._value; }
}

// === abstract class ===
abstract class Animal {
    abstract speak(): string;
    move(): void { console.log("moving"); }
}

// === as / satisfies / non-null assertion ===
const val = someValue as string;
const p = { x: 1, y: 2 } satisfies Point;
const el = document.getElementById("app")!;

// === namespace ===
namespace Geometry {
    export function area(r: number): number { return Math.PI * r * r; }
}

// === decorator ===
function sealed(constructor: Function) {}

@sealed
class Greeter {
    greeting: string;
    constructor(message: string) { this.greeting = message; }
}

// === mapped types / conditional types ===
type Readonly2<T> = { readonly [P in keyof T]: T[P] };
type NonNullable2<T> = T extends null | undefined ? never : T;

// === tuple types ===
let tuple: [string, number] = ["hello", 42];

// === intersection type ===
type Combined = Shape & { color: string };

// === type guard ===
function isString(val: any): val is string {
    return typeof val === "string";
}

// === import type ===
import type { SomeType } from "module";

// === optional parameter ===
function greet(name: string, greeting?: string): string {
    return `${greeting ?? "Hello"}, ${name}`;
}

// === rest parameters ===
function sum(...nums: number[]): number {
    return nums.reduce((a, b) => a + b, 0);
}

// === assertion functions ===
function assertDefined<T>(val: T | undefined): asserts val is T {
    if (val === undefined) throw new Error("undefined");
}
"""

SOURCES["java"] = r'''
import java.util.*;
import java.util.stream.*;
import java.io.*;

public class Main {
    // === fields ===
    private int x = 10;
    public static final String NAME = "Java";
    volatile boolean running = true;

    // === constructor ===
    public Main(int x) { this.x = x; }

    // === method with generics ===
    public <T extends Comparable<T>> T max(T a, T b) {
        return a.compareTo(b) > 0 ? a : b;
    }

    // === enhanced for ===
    public void iterate(List<String> items) {
        for (String item : items) {
            System.out.println(item);
        }
    }

    // === try-with-resources ===
    public void readFile(String path) throws IOException {
        try (BufferedReader br = new BufferedReader(new FileReader(path))) {
            String line;
            while ((line = br.readLine()) != null) {
                System.out.println(line);
            }
        } catch (FileNotFoundException e) {
            throw new RuntimeException(e);
        } finally {
            System.out.println("done");
        }
    }

    // === switch expression (Java 14+) ===
    public String dayType(int day) {
        return switch (day) {
            case 1, 7 -> "weekend";
            case 2, 3, 4, 5, 6 -> "weekday";
            default -> throw new IllegalArgumentException();
        };
    }

    // === lambda ===
    public void lambdas() {
        Runnable r = () -> System.out.println("run");
        Comparator<String> cmp = (a, b) -> a.compareTo(b);
        Function<Integer, Integer> square = x -> x * x;
    }

    // === streams ===
    public List<String> filterNames(List<String> names) {
        return names.stream()
            .filter(n -> n.startsWith("A"))
            .map(String::toUpperCase)
            .collect(Collectors.toList());
    }

    // === instanceof pattern matching (Java 16+) ===
    public String describe(Object obj) {
        if (obj instanceof String s) {
            return "String: " + s;
        }
        return "Other";
    }

    // === record (Java 16+) ===
    public record Point(int x, int y) {}

    // === sealed class (Java 17+) ===
    public sealed interface Shape permits Circle, Square {}
    public record Circle(double radius) implements Shape {}
    public record Square(double side) implements Shape {}

    // === text block ===
    String json = """
        {
            "key": "value"
        }
        """;

    // === array creation ===
    int[] arr = new int[]{1, 2, 3};
    int[][] matrix = new int[3][4];

    // === assert ===
    public void check(int x) {
        assert x > 0 : "must be positive";
    }

    // === synchronized ===
    public synchronized void sync() {}

    // === annotation ===
    @Override
    public String toString() { return "Main"; }

    // === inner class ===
    class Inner { int val; }

    // === enum ===
    enum Status { ACTIVE, INACTIVE }

    // === interface with default method ===
    interface Printable {
        void print();
        default void println() { print(); System.out.println(); }
    }

    // === ternary ===
    int val = x > 0 ? x : -x;

    // === cast ===
    Object o = "hello";
    String s = (String) o;

    // === static initializer ===
    static {
        System.out.println("static init");
    }

    // === do-while ===
    public void doWhile() {
        int i = 0;
        do { i++; } while (i < 10);
    }

    // === labeled break ===
    public void labeledBreak() {
        outer:
        for (int i = 0; i < 10; i++) {
            for (int j = 0; j < 10; j++) {
                if (j == 5) break outer;
            }
        }
    }

    // === varargs ===
    public int sum(int... nums) {
        int total = 0;
        for (int n : nums) total += n;
        return total;
    }

    // === multi-catch ===
    public void multiCatch() {
        try {
            risky();
        } catch (IOException | RuntimeException e) {
            handle(e);
        }
    }
}
'''

SOURCES["ruby"] = r"""
# === basic assignments ===
x = 1
y = "hello"
a, b, c = 1, 2, 3
*head, tail = [1, 2, 3, 4]

# === string interpolation ===
msg = "Hello #{name}!"
msg2 = "Value: #{x + y}"

# === symbols ===
sym = :my_symbol
sym_str = :"dynamic_#{x}"

# === if / unless / ternary ===
if x > 0
  puts "positive"
elsif x == 0
  puts "zero"
else
  puts "negative"
end

unless done
  work()
end

result = x > 0 ? "yes" : "no"
puts "big" if x > 100
puts "small" unless x > 100

# === case / when ===
case value
when 1
  "one"
when 2, 3
  "two or three"
when String
  "string"
when /pattern/
  "regex match"
else
  "other"
end

# === loops ===
while x > 0
  x -= 1
end

until x >= 10
  x += 1
end

for i in 0..9
  puts i
end

5.times { |i| puts i }
[1, 2, 3].each { |x| puts x }
(1..10).map { |x| x * 2 }
[1, 2, 3].select { |x| x > 1 }
[1, 2, 3].reduce(0) { |acc, x| acc + x }

# === begin/rescue/else/ensure ===
begin
  risky()
rescue StandardError => e
  handle(e)
rescue TypeError, ArgumentError
  retry
else
  success()
ensure
  cleanup()
end

# === method def ===
def greet(name, greeting = "Hello")
  "#{greeting}, #{name}!"
end

def variadic(*args, **kwargs)
  args.length
end

# === class ===
class Animal
  attr_accessor :name, :age

  def initialize(name, age)
    @name = name
    @age = age
  end

  def speak
    raise NotImplementedError
  end

  def <=>(other)
    @age <=> other.age
  end

  private

  def secret
    "hidden"
  end
end

class Dog < Animal
  def speak
    "Woof!"
  end
end

# === module / mixin ===
module Greetable
  def greet
    "Hello, I'm #{name}"
  end
end

# === proc / lambda ===
square = Proc.new { |x| x * x }
double = lambda { |x| x * 2 }
triple = ->(x) { x * 3 }

# === blocks ===
def with_logging(&block)
  puts "start"
  block.call
  puts "end"
end

# === yield ===
def each_pair(arr)
  arr.each_slice(2) { |pair| yield pair }
end

# === method_missing / define_method ===
class Dynamic
  def method_missing(name, *args)
    puts "called #{name}"
  end

  %w[foo bar baz].each do |m|
    define_method(m) { puts m }
  end
end

# === range ===
r = 1..10
r2 = 1...10

# === hash ===
h = {a: 1, b: 2, "c" => 3}

# === array ===
arr = [1, "two", :three, [4, 5]]

# === regex ===
if "hello" =~ /^he/
  puts $~
end

# === heredoc ===
text = <<~HEREDOC
  Hello
  World
HEREDOC

# === ternary operator ===
status = age >= 18 ? "adult" : "minor"

# === splat and double splat ===
def merge_opts(*args, **opts)
  opts
end
"""

SOURCES["go"] = r"""
package main

import (
    "fmt"
    "sync"
    "time"
)

// === struct ===
type Point struct {
    X, Y int
}

// === interface ===
type Shape interface {
    Area() float64
    Perimeter() float64
}

// === struct with methods ===
type Circle struct {
    Radius float64
}

func (c Circle) Area() float64 {
    return 3.14159 * c.Radius * c.Radius
}

func (c *Circle) Scale(factor float64) {
    c.Radius *= factor
}

// === function with multiple return values ===
func divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("division by zero")
    }
    return a / b, nil
}

// === goroutine ===
func startWorker(id int, wg *sync.WaitGroup) {
    defer wg.Done()
    fmt.Printf("Worker %d starting\n", id)
    time.Sleep(time.Second)
    fmt.Printf("Worker %d done\n", id)
}

// === channels ===
func producer(ch chan<- int) {
    for i := 0; i < 5; i++ {
        ch <- i
    }
    close(ch)
}

func consumer(ch <-chan int) {
    for val := range ch {
        fmt.Println(val)
    }
}

// === select ===
func selectExample(ch1, ch2 chan int, done chan bool) {
    select {
    case v := <-ch1:
        fmt.Println("ch1:", v)
    case v := <-ch2:
        fmt.Println("ch2:", v)
    case <-done:
        return
    default:
        fmt.Println("no data")
    }
}

// === type switch ===
func typeSwitch(i interface{}) {
    switch v := i.(type) {
    case int:
        fmt.Println("int:", v)
    case string:
        fmt.Println("string:", v)
    default:
        fmt.Println("unknown")
    }
}

// === map literal ===
func maps() {
    m := map[string]int{
        "one": 1,
        "two": 2,
    }
    m["three"] = 3
    delete(m, "one")

    if val, ok := m["two"]; ok {
        fmt.Println(val)
    }

    for k, v := range m {
        fmt.Printf("%s: %d\n", k, v)
    }
}

// === slice expressions ===
func slices() {
    s := []int{1, 2, 3, 4, 5}
    sub := s[1:3]
    sub2 := s[:3]
    sub3 := s[2:]
    full := s[:]
    _ = sub
    _ = sub2
    _ = sub3
    _ = full

    s = append(s, 6, 7)
    dst := make([]int, len(s))
    copy(dst, s)
}

// === embedding ===
type Base struct {
    ID int
}

type Derived struct {
    Base
    Name string
}

// === defer ===
func withDefer() {
    defer fmt.Println("deferred")
    fmt.Println("normal")
}

// === panic / recover ===
func safeDiv(a, b int) (result int, err error) {
    defer func() {
        if r := recover(); r != nil {
            err = fmt.Errorf("panic: %v", r)
        }
    }()
    return a / b, nil
}

// === go statement ===
func main() {
    var wg sync.WaitGroup
    for i := 0; i < 3; i++ {
        wg.Add(1)
        go startWorker(i, &wg)
    }
    wg.Wait()

    ch := make(chan int, 5)
    go producer(ch)
    consumer(ch)
}

// === const / iota ===
const (
    A = iota
    B
    C
)

// === type alias ===
type Meter float64
type Callback func(int) error

// === blank identifier ===
func blank() {
    _, err := divide(10, 0)
    _ = err
}

// === composite literal ===
func composites() {
    p := Point{X: 1, Y: 2}
    arr := [3]int{1, 2, 3}
    _ = p
    _ = arr
}

// === variadic ===
func sum(nums ...int) int {
    total := 0
    for _, n := range nums {
        total += n
    }
    return total
}

// === labeled break/continue ===
func labeled() {
outer:
    for i := 0; i < 10; i++ {
        for j := 0; j < 10; j++ {
            if j == 5 {
                break outer
            }
            continue outer
        }
    }
}
"""

SOURCES["php"] = r"""
<?php
// === variable declarations ===
$x = 1;
$y = "hello";
$arr = [1, 2, 3];
$assoc = ["key" => "value", "num" => 42];

// === string interpolation ===
$msg = "Hello {$name}!";
$msg2 = "Value: ${x}";
$heredoc = <<<EOT
Hello {$name}
World
EOT;

// === nowdoc ===
$nowdoc = <<<'EOT'
No interpolation here
EOT;

// === functions ===
function add(int $a, int $b): int {
    return $a + $b;
}

function variadic(string ...$args): void {
    foreach ($args as $arg) {
        echo $arg;
    }
}

// === arrow function ===
$double = fn($x) => $x * 2;

// === anonymous function / closure ===
$greet = function($name) use ($greeting) {
    return "$greeting, $name!";
};

// === class ===
class Animal {
    private string $name;
    protected int $age;
    public static int $count = 0;

    public function __construct(string $name, int $age) {
        $this->name = $name;
        $this->age = $age;
        self::$count++;
    }

    public function getName(): string {
        return $this->name;
    }

    public static function getCount(): int {
        return self::$count;
    }

    public function __toString(): string {
        return $this->name;
    }
}

// === interface ===
interface Printable {
    public function print(): void;
}

// === trait ===
trait Loggable {
    public function log(string $msg): void {
        echo $msg;
    }
}

class Dog extends Animal implements Printable {
    use Loggable;

    public function print(): void {
        echo $this->getName();
    }

    public function speak(): string {
        return "Woof!";
    }
}

// === abstract class ===
abstract class Shape {
    abstract public function area(): float;
}

// === enum (PHP 8.1+) ===
enum Suit: string {
    case Hearts = 'H';
    case Diamonds = 'D';
    case Clubs = 'C';
    case Spades = 'S';
}

// === match expression (PHP 8.0+) ===
$result = match($status) {
    200 => "OK",
    404 => "Not Found",
    500 => "Server Error",
    default => "Unknown",
};

// === null coalescing ===
$val = $data ?? "default";
$data ??= "fallback";

// === named arguments (PHP 8.0+) ===
function createUser(string $name, int $age, string $role = "user") {}
createUser(name: "Alice", age: 30);

// === try/catch/finally ===
try {
    risky();
} catch (RuntimeException | LogicException $e) {
    handle($e);
} catch (Exception $e) {
    fallback($e);
} finally {
    cleanup();
}

// === foreach ===
foreach ($arr as $val) {
    process($val);
}
foreach ($assoc as $key => $val) {
    echo "$key: $val";
}

// === for ===
for ($i = 0; $i < 10; $i++) {
    echo $i;
}

// === while / do-while ===
while ($x > 0) { $x--; }
do { $x++; } while ($x < 10);

// === switch ===
switch ($action) {
    case "start": begin(); break;
    case "stop": end_action(); break;
    default: idle();
}

// === null safe operator (PHP 8.0+) ===
$country = $user?->getAddress()?->getCountry();

// === spread operator ===
$merged = [...$arr1, ...$arr2];
function spreadCall(int ...$nums): int { return array_sum($nums); }

// === list() / short list ===
[$a, $b, $c] = [1, 2, 3];
list($x, $y) = [10, 20];

// === type casting ===
$intVal = (int)"42";
$strVal = (string)42;

// === static properties/methods ===
$count = Animal::$count;
$c = Animal::getCount();

// === instanceof ===
if ($dog instanceof Animal) {
    echo "is animal";
}

// === global ===
function useGlobal() {
    global $config;
    return $config;
}

// === include/require ===
include "header.php";
require_once "config.php";
?>
"""

SOURCES["c_sharp"] = r"""
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace AuditSample
{
    // === class ===
    public class Person
    {
        // === properties ===
        public string Name { get; set; }
        public int Age { get; private set; }
        public string FullName => $"{Name} (age {Age})";

        // === constructor ===
        public Person(string name, int age)
        {
            Name = name;
            Age = age;
        }

        // === method ===
        public override string ToString() => $"Person({Name}, {Age})";

        // === deconstruct ===
        public void Deconstruct(out string name, out int age)
        {
            name = Name;
            age = Age;
        }
    }

    // === record ===
    public record Point(int X, int Y);

    // === interface ===
    public interface IShape
    {
        double Area();
        double Perimeter() => 0;
    }

    // === struct ===
    public struct Color
    {
        public byte R, G, B;
    }

    // === enum ===
    public enum Direction { North, South, East, West }

    [Flags]
    public enum Permissions { None = 0, Read = 1, Write = 2, Execute = 4 }

    // === abstract class ===
    public abstract class Shape : IShape
    {
        public abstract double Area();
    }

    // === generic class ===
    public class Stack<T>
    {
        private readonly List<T> _items = new();
        public void Push(T item) => _items.Add(item);
        public T Pop() { var item = _items[^1]; _items.RemoveAt(_items.Count - 1); return item; }
    }

    // === extension method ===
    public static class StringExtensions
    {
        public static bool IsNullOrEmpty(this string s) => string.IsNullOrEmpty(s);
    }

    // === async/await ===
    public class AsyncExample
    {
        public async Task<string> FetchAsync(string url)
        {
            await Task.Delay(100);
            return "data";
        }

        public async IAsyncEnumerable<int> GenerateAsync()
        {
            for (int i = 0; i < 10; i++)
            {
                await Task.Delay(10);
                yield return i;
            }
        }
    }

    // === switch expression ===
    public class Patterns
    {
        public string Classify(object obj) => obj switch
        {
            int i when i > 0 => "positive int",
            string s => $"string: {s}",
            null => "null",
            _ => "other"
        };

        // === pattern matching ===
        public void PatternMatch(object x)
        {
            if (x is string { Length: > 5 } s)
            {
                Console.WriteLine(s);
            }

            if (x is int and > 0)
            {
                Console.WriteLine("positive");
            }
        }
    }

    // === LINQ ===
    public class LinqExamples
    {
        public void Query()
        {
            var nums = new[] { 1, 2, 3, 4, 5 };
            var evens = from n in nums where n % 2 == 0 select n;
            var doubled = nums.Select(x => x * 2).ToList();
        }
    }

    // === try/catch/finally ===
    public class ErrorHandling
    {
        public void Handle()
        {
            try
            {
                throw new InvalidOperationException("oops");
            }
            catch (InvalidOperationException ex) when (ex.Message.Contains("oops"))
            {
                Console.WriteLine(ex);
            }
            catch (Exception ex)
            {
                Console.WriteLine(ex);
            }
            finally
            {
                Console.WriteLine("cleanup");
            }
        }
    }

    // === using statement / declaration ===
    public class ResourceExample
    {
        public void UseResource()
        {
            using var stream = new System.IO.MemoryStream();
            using (var reader = new System.IO.StreamReader(stream))
            {
                var content = reader.ReadToEnd();
            }
        }
    }

    // === delegate / event ===
    public delegate void Notify(string message);

    public class EventExample
    {
        public event Notify OnNotify;

        public void Trigger() => OnNotify?.Invoke("hello");
    }

    // === nullable types ===
    public class NullableExample
    {
        public void Test()
        {
            int? x = null;
            var y = x ?? 42;
            var z = x?.ToString() ?? "null";
        }
    }

    // === tuple ===
    public class TupleExample
    {
        public (string Name, int Age) GetPerson() => ("Alice", 30);

        public void Use()
        {
            var (name, age) = GetPerson();
        }
    }

    // === foreach / for / while / do-while ===
    public class Loops
    {
        public void AllLoops()
        {
            foreach (var item in new[] { 1, 2, 3 }) { }
            for (int i = 0; i < 10; i++) { }
            while (true) { break; }
            do { } while (false);
        }
    }

    // === lock ===
    public class ThreadSafe
    {
        private readonly object _lock = new();
        public void Safe() { lock (_lock) { } }
    }

    // === interpolated string ===
    public class Strings
    {
        public string Format(string name) => $"Hello, {name}!";
        public string Verbatim() => @"C:\Users\test";
        public string Raw() => $@"Path: {name}\file";
    }
}
"""

SOURCES["c"] = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// === function declarations ===
int add(int a, int b) { return a + b; }
void noop(void) {}
static inline int square(int x) { return x * x; }
extern int extern_func(int a);
int variadic(int count, ...) { return 0; }

// === structs ===
struct Point { int x; int y; };
struct Node { int val; struct Node* next; };
typedef struct { int r; int g; int b; } Color;

// === unions ===
union Data { int i; float f; char c; };

// === enums ===
enum Direction { NORTH = 0, SOUTH, EAST, WEST };
typedef enum { FALSE_VAL = 0, TRUE_VAL = 1 } Boolean;

// === typedef ===
typedef int Integer;
typedef void (*FuncPtr)(int);

// === global variables ===
int global_var = 42;
const int const_var = 100;
static int static_var = 0;

// === pointer arithmetic ===
void pointers() {
    int arr[] = {1, 2, 3, 4, 5};
    int *p = arr;
    int val = *(p + 2);
    p++;
    int diff = p - arr;
    int *q = &arr[3];
    int deref = *q;
}

// === arrays ===
void arrays() {
    int fixed[10] = {0};
    char str[] = "hello";
    int matrix[3][4] = {{1,2,3,4},{5,6,7,8},{9,10,11,12}};
    int *dynamic = (int*)malloc(10 * sizeof(int));
    free(dynamic);
}

// === control flow ===
void control() {
    // if/else
    int x = 10;
    if (x > 5) {
        printf("big\n");
    } else if (x > 0) {
        printf("small\n");
    } else {
        printf("negative\n");
    }

    // switch
    switch (x) {
        case 1: printf("one\n"); break;
        case 2: printf("two\n"); break;
        default: printf("other\n"); break;
    }

    // for
    for (int i = 0; i < 10; i++) {
        if (i == 5) break;
        if (i == 3) continue;
        printf("%d\n", i);
    }

    // while
    while (x > 0) { x--; }

    // do-while
    do { x++; } while (x < 10);

    // goto
    goto end;
    printf("skipped\n");
    end:
    printf("done\n");
}

// === function pointers ===
void apply(int *arr, int n, int (*fn)(int)) {
    for (int i = 0; i < n; i++) {
        arr[i] = fn(arr[i]);
    }
}

// === sizeof / cast ===
void misc() {
    int x = 42;
    size_t sz = sizeof(x);
    double d = (double)x;
    void *vp = (void*)&x;
    int *ip = (int*)vp;
    unsigned char uc = (unsigned char)x;
}

// === bitwise ===
void bitwise() {
    int a = 0xFF;
    int b = a & 0x0F;
    int c = a | 0xF0;
    int d = a ^ 0xFF;
    int e = ~a;
    int f = a << 4;
    int g = a >> 2;
}

// === ternary ===
int ternary(int x) {
    return x > 0 ? x : -x;
}

// === comma operator ===
void comma() {
    int a, b;
    for (a = 0, b = 10; a < b; a++, b--) {}
}

// === compound literal ===
void compound() {
    struct Point p = (struct Point){.x = 1, .y = 2};
}

// === string operations ===
void strings() {
    char buf[100];
    strcpy(buf, "hello");
    strcat(buf, " world");
    int len = strlen(buf);
    int cmp = strcmp(buf, "hello world");
}

// === macro-like patterns ===
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define PI 3.14159

// === static_assert (C11) ===
_Static_assert(sizeof(int) >= 4, "int too small");
"""

SOURCES["cpp"] = r"""
#include <iostream>
#include <vector>
#include <string>
#include <memory>
#include <algorithm>
#include <functional>
#include <map>
#include <optional>

// === namespace ===
namespace math {
    constexpr double PI = 3.14159265358979;

    template<typename T>
    T max(T a, T b) { return a > b ? a : b; }
}

// === class with rule of five ===
class Buffer {
    char* data;
    size_t size;
public:
    Buffer(size_t sz) : data(new char[sz]), size(sz) {}
    ~Buffer() { delete[] data; }
    Buffer(const Buffer& other) : data(new char[other.size]), size(other.size) {
        std::copy(other.data, other.data + size, data);
    }
    Buffer(Buffer&& other) noexcept : data(other.data), size(other.size) {
        other.data = nullptr; other.size = 0;
    }
    Buffer& operator=(const Buffer&) = default;
    Buffer& operator=(Buffer&&) noexcept = default;
};

// === templates ===
template<typename T, int N>
class FixedArray {
    T data[N];
public:
    T& operator[](int i) { return data[i]; }
    constexpr int size() const { return N; }
};

// === template specialization ===
template<> class FixedArray<bool, 8> {
    unsigned char bits = 0;
public:
    bool get(int i) const { return (bits >> i) & 1; }
    void set(int i, bool v) { if (v) bits |= (1 << i); else bits &= ~(1 << i); }
};

// === inheritance ===
class Shape {
public:
    virtual double area() const = 0;
    virtual ~Shape() = default;
};

class Circle : public Shape {
    double radius;
public:
    Circle(double r) : radius(r) {}
    double area() const override { return math::PI * radius * radius; }
};

// === smart pointers ===
void smartPointers() {
    auto unique = std::make_unique<Circle>(5.0);
    auto shared = std::make_shared<Circle>(3.0);
    std::weak_ptr<Circle> weak = shared;
}

// === lambdas ===
void lambdas() {
    auto add = [](int a, int b) { return a + b; };
    int x = 10;
    auto capture = [x](int y) { return x + y; };
    auto mutable_cap = [x]() mutable { x++; return x; };
    auto generic = [](auto a, auto b) { return a + b; };
}

// === range-based for ===
void rangeFor() {
    std::vector<int> v{1, 2, 3, 4, 5};
    for (const auto& elem : v) { std::cout << elem; }
    for (auto&& [key, val] : std::map<std::string, int>{{"a", 1}}) {}
}

// === structured bindings ===
void structuredBindings() {
    auto [x, y] = std::make_pair(1, 2);
    auto [a, b, c] = std::make_tuple(1, "hello", 3.14);
}

// === if constexpr ===
template<typename T>
void process(T val) {
    if constexpr (std::is_integral_v<T>) {
        std::cout << "integral: " << val;
    } else {
        std::cout << "other: " << val;
    }
}

// === optional ===
std::optional<int> findValue(const std::vector<int>& v, int target) {
    for (const auto& elem : v) {
        if (elem == target) return elem;
    }
    return std::nullopt;
}

// === try/catch ===
void tryCatch() {
    try {
        throw std::runtime_error("oops");
    } catch (const std::runtime_error& e) {
        std::cerr << e.what();
    } catch (...) {
        std::cerr << "unknown error";
    }
}

// === enum class ===
enum class Color { Red, Green, Blue };

// === constexpr ===
constexpr int factorial(int n) {
    return n <= 1 ? 1 : n * factorial(n - 1);
}

// === auto return type ===
auto multiply(int a, int b) -> int { return a * b; }

// === static_assert ===
static_assert(sizeof(int) >= 4, "need 32-bit ints");

// === new/delete ===
void newDelete() {
    int* p = new int(42);
    delete p;
    int* arr = new int[10];
    delete[] arr;
}

// === reinterpret_cast, static_cast, dynamic_cast, const_cast ===
void casts() {
    int x = 42;
    double d = static_cast<double>(x);
    const int& cr = x;
    int& r = const_cast<int&>(cr);
    void* vp = reinterpret_cast<void*>(&x);
}

// === using ===
using IntVec = std::vector<int>;
using namespace std;

// === initializer list ===
class Container {
    std::vector<int> data;
public:
    Container(std::initializer_list<int> init) : data(init) {}
};

// === concepts (C++20) ===
template<typename T>
concept Numeric = std::is_arithmetic_v<T>;

template<Numeric T>
T add(T a, T b) { return a + b; }
"""

SOURCES["rust"] = r"""
use std::collections::HashMap;
use std::fmt;

// === struct ===
#[derive(Debug, Clone)]
struct Point {
    x: f64,
    y: f64,
}

// === impl block ===
impl Point {
    fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }

    fn distance(&self, other: &Point) -> f64 {
        ((self.x - other.x).powi(2) + (self.y - other.y).powi(2)).sqrt()
    }
}

// === trait ===
trait Shape {
    fn area(&self) -> f64;
    fn perimeter(&self) -> f64;
    fn describe(&self) -> String {
        format!("Area: {}", self.area())
    }
}

// === impl trait for struct ===
struct Circle {
    radius: f64,
}

impl Shape for Circle {
    fn area(&self) -> f64 {
        std::f64::consts::PI * self.radius * self.radius
    }
    fn perimeter(&self) -> f64 {
        2.0 * std::f64::consts::PI * self.radius
    }
}

impl fmt::Display for Circle {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Circle(r={})", self.radius)
    }
}

// === enum with data ===
#[derive(Debug)]
enum Message {
    Quit,
    Move { x: i32, y: i32 },
    Write(String),
    Color(i32, i32, i32),
}

// === pattern matching ===
fn handle_message(msg: &Message) {
    match msg {
        Message::Quit => println!("quit"),
        Message::Move { x, y } => println!("move to {},{}", x, y),
        Message::Write(text) => println!("write: {}", text),
        Message::Color(r, g, b) if *r > 128 => println!("bright color"),
        Message::Color(r, g, b) => println!("color: {},{},{}", r, g, b),
    }
}

// === if let / while let ===
fn optional_patterns() {
    let opt: Option<i32> = Some(42);

    if let Some(val) = opt {
        println!("got: {}", val);
    }

    let mut stack = vec![1, 2, 3];
    while let Some(top) = stack.pop() {
        println!("top: {}", top);
    }
}

// === closures ===
fn closures() {
    let add = |a, b| a + b;
    let x = 10;
    let add_x = |y| x + y;
    let mut count = 0;
    let mut increment = || { count += 1; count };
    increment();

    let nums = vec![1, 2, 3, 4, 5];
    let doubled: Vec<i32> = nums.iter().map(|x| x * 2).collect();
    let evens: Vec<&i32> = nums.iter().filter(|x| **x % 2 == 0).collect();
}

// === Result / Option chaining ===
fn parse_and_add(a: &str, b: &str) -> Result<i32, String> {
    let x = a.parse::<i32>().map_err(|e| e.to_string())?;
    let y = b.parse::<i32>().map_err(|e| e.to_string())?;
    Ok(x + y)
}

// === loop ===
fn loop_example() {
    let mut count = 0;
    let result = loop {
        count += 1;
        if count == 10 {
            break count * 2;
        }
    };
}

// === for loop ===
fn for_loops() {
    for i in 0..10 {
        println!("{}", i);
    }
    for i in (0..10).rev() {
        println!("{}", i);
    }
    let v = vec![1, 2, 3];
    for (i, val) in v.iter().enumerate() {
        println!("{}: {}", i, val);
    }
}

// === generics ===
fn largest<T: PartialOrd>(list: &[T]) -> &T {
    let mut largest = &list[0];
    for item in &list[1..] {
        if item > largest {
            largest = item;
        }
    }
    largest
}

// === lifetime annotations ===
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// === macro invocations ===
fn macros() {
    println!("hello {}", "world");
    let v = vec![1, 2, 3];
    let m = HashMap::from([("key", "value")]);
    assert_eq!(2 + 2, 4);
    assert!(true);
    todo!();
}

// === struct update syntax ===
fn struct_update() {
    let p1 = Point::new(1.0, 2.0);
    let p2 = Point { x: 5.0, ..p1 };
}

// === type alias ===
type Thunk = Box<dyn Fn() + Send + 'static>;
type Result2<T> = std::result::Result<T, String>;

// === const / static ===
const MAX_POINTS: u32 = 100_000;
static HELLO_WORLD: &str = "Hello, world!";

// === unsafe ===
unsafe fn dangerous() {}

fn use_unsafe() {
    unsafe {
        dangerous();
    }
}

// === async ===
async fn fetch_data() -> String {
    "data".to_string()
}

// === box / dyn ===
fn create_shape() -> Box<dyn Shape> {
    Box::new(Circle { radius: 5.0 })
}

// === let else (Rust 1.65+) ===
fn let_else(opt: Option<i32>) {
    let Some(val) = opt else {
        return;
    };
    println!("{}", val);
}
"""

SOURCES["kotlin"] = r"""
import kotlin.math.PI

// === data class ===
data class Point(val x: Double, val y: Double)

// === sealed class ===
sealed class Shape {
    data class Circle(val radius: Double) : Shape()
    data class Rectangle(val width: Double, val height: Double) : Shape()
    data object Unknown : Shape()
}

// === when expression (pattern matching) ===
fun describeShape(shape: Shape): String = when (shape) {
    is Shape.Circle -> "Circle with radius ${shape.radius}"
    is Shape.Rectangle -> "Rectangle ${shape.width}x${shape.height}"
    Shape.Unknown -> "Unknown shape"
}

// === extension function ===
fun String.isPalindrome(): Boolean = this == this.reversed()

// === null safety ===
fun nullSafety() {
    val name: String? = null
    val length = name?.length ?: 0
    val upper = name?.uppercase()
    val forced = name!!
}

// === lambda / higher-order functions ===
fun <T> Collection<T>.customFilter(predicate: (T) -> Boolean): List<T> {
    val result = mutableListOf<T>()
    for (item in this) {
        if (predicate(item)) result.add(item)
    }
    return result
}

fun lambdas() {
    val nums = listOf(1, 2, 3, 4, 5)
    val doubled = nums.map { it * 2 }
    val evens = nums.filter { it % 2 == 0 }
    val sum = nums.fold(0) { acc, n -> acc + n }
    val sorted = nums.sortedBy { -it }
}

// === coroutines (conceptual, no actual suspend) ===
suspend fun fetchData(): String {
    return "data"
}

// === object / companion object ===
object Singleton {
    val name = "Singleton"
    fun greet() = "Hello from $name"
}

class MyClass {
    companion object {
        const val TAG = "MyClass"
        fun create(): MyClass = MyClass()
    }
}

// === interface ===
interface Printable {
    fun print()
    fun prettyPrint() { print() }
}

// === enum class ===
enum class Direction {
    NORTH, SOUTH, EAST, WEST;

    fun opposite(): Direction = when (this) {
        NORTH -> SOUTH
        SOUTH -> NORTH
        EAST -> WEST
        WEST -> EAST
    }
}

// === string templates ===
fun templates() {
    val name = "Kotlin"
    val greeting = "Hello, $name!"
    val calc = "Result: ${1 + 2}"
}

// === try/catch/finally ===
fun tryCatch() {
    try {
        throw IllegalArgumentException("oops")
    } catch (e: IllegalArgumentException) {
        println(e.message)
    } catch (e: Exception) {
        println("generic: ${e.message}")
    } finally {
        println("cleanup")
    }
}

// === destructuring ===
fun destructuring() {
    val (x, y) = Point(1.0, 2.0)
    val map = mapOf("a" to 1, "b" to 2)
    for ((key, value) in map) {
        println("$key: $value")
    }
}

// === ranges ===
fun ranges() {
    for (i in 1..10) { }
    for (i in 10 downTo 1 step 2) { }
    for (i in 0 until 10) { }
    val inRange = 5 in 1..10
}

// === type checks / smart casts ===
fun smartCast(obj: Any) {
    if (obj is String) {
        println(obj.length)
    }
    when (obj) {
        is Int -> println("int: $obj")
        is String -> println("string: $obj")
        else -> println("other")
    }
}

// === property delegation ===
class Lazy {
    val lazyVal: String by lazy { "computed" }
}

// === inline function ===
inline fun <reified T> isType(value: Any): Boolean = value is T

// === vararg ===
fun printAll(vararg messages: String) {
    for (m in messages) println(m)
}

// === operator overloading ===
operator fun Point.plus(other: Point) = Point(x + other.x, y + other.y)

// === scope functions ===
fun scopeFunctions() {
    val result = "Hello".let { it.uppercase() }
    val person = Point(1.0, 2.0).also { println(it) }
    val applied = Point(1.0, 2.0).apply { }
    with(Point(1.0, 2.0)) { println("$x, $y") }
    val ran = Point(1.0, 2.0).run { x + y }
}

// === do-while ===
fun doWhile() {
    var x = 0
    do { x++ } while (x < 10)
}

// === labeled break/continue ===
fun labeled() {
    outer@ for (i in 1..10) {
        for (j in 1..10) {
            if (j == 5) break@outer
            if (j == 3) continue@outer
        }
    }
}

// === annotations ===
@Deprecated("Use newMethod instead")
fun oldMethod() {}

// === typealias ===
typealias StringList = List<String>
typealias Predicate<T> = (T) -> Boolean
"""

SOURCES["scala"] = r"""
import scala.collection.mutable
import scala.util.{Try, Success, Failure}

// === case class ===
case class Point(x: Double, y: Double)

// === sealed trait + case classes (ADT) ===
sealed trait Shape
case class Circle(radius: Double) extends Shape
case class Rectangle(width: Double, height: Double) extends Shape
case object Unknown extends Shape

// === object (singleton) ===
object MathUtils {
  val PI: Double = 3.14159
  def square(x: Double): Double = x * x
  def cube(x: Double): Double = x * x * x
}

// === class with constructor ===
class Person(val name: String, var age: Int) {
  def greet(): String = s"Hello, I'm $name, age $age"
  override def toString: String = s"Person($name, $age)"
}

// === trait with abstract and concrete methods ===
trait Printable {
  def print(): Unit
  def prettyPrint(): Unit = {
    print()
    println()
  }
}

// === pattern matching ===
def describeShape(shape: Shape): String = shape match {
  case Circle(r) => s"Circle with radius $r"
  case Rectangle(w, h) => s"Rectangle ${w}x${h}"
  case Unknown => "Unknown shape"
}

def matchExample(x: Any): String = x match {
  case i: Int if i > 0 => s"positive int: $i"
  case s: String => s"string: $s"
  case (a, b) => s"tuple: ($a, $b)"
  case head :: tail => s"list head: $head"
  case _ => "other"
}

// === for comprehension ===
def forComprehension(): Unit = {
  val nums = List(1, 2, 3, 4, 5)
  val doubled = for (n <- nums) yield n * 2
  val evens = for (n <- nums if n % 2 == 0) yield n

  for {
    x <- List(1, 2, 3)
    y <- List("a", "b")
  } println(s"$x$y")
}

// === higher-order functions ===
def higherOrder(): Unit = {
  val nums = List(1, 2, 3, 4, 5)
  val doubled = nums.map(_ * 2)
  val evens = nums.filter(_ % 2 == 0)
  val sum = nums.foldLeft(0)(_ + _)
  val product = nums.reduce(_ * _)
  nums.foreach(println)
}

// === Option / Either / Try ===
def optionExample(): Unit = {
  val opt: Option[Int] = Some(42)
  val none: Option[Int] = None

  val result = opt match {
    case Some(v) => s"Got: $v"
    case None => "Nothing"
  }

  val mapped = opt.map(_ * 2).getOrElse(0)
  val flat = opt.flatMap(v => if (v > 0) Some(v) else None)
}

def tryExample(): Unit = {
  val result = Try(42 / 0) match {
    case Success(v) => s"Success: $v"
    case Failure(e) => s"Failure: ${e.getMessage}"
  }
}

// === string interpolation ===
def stringInterp(): Unit = {
  val name = "Scala"
  val greeting = s"Hello, $name!"
  val calc = s"Result: ${1 + 2}"
  val formatted = f"Pi is $MathUtils.PI%.4f"
  val raw = raw"No \n escape"
}

// === implicit / given (Scala 3 style as conceptual) ===
implicit class RichInt(val n: Int) extends AnyVal {
  def isEven: Boolean = n % 2 == 0
  def isOdd: Boolean = !isEven
}

// === lazy val ===
lazy val expensiveComputation: Int = {
  println("computing...")
  42
}

// === while / do-while ===
def loops(): Unit = {
  var i = 0
  while (i < 10) { i += 1 }

  var j = 0
  // do-while via while with pre-check
  while ({ j += 1; j < 10 }) {}
}

// === try/catch/finally ===
def errorHandling(): Unit = {
  try {
    throw new RuntimeException("oops")
  } catch {
    case e: RuntimeException => println(e.getMessage)
    case e: Exception => println("generic error")
  } finally {
    println("cleanup")
  }
}

// === type alias ===
type StringList = List[String]
type Predicate[T] = T => Boolean

// === abstract class ===
abstract class Animal {
  def speak(): String
  def name: String
}

class Dog(val name: String) extends Animal {
  def speak(): String = "Woof!"
}

// === companion object ===
class Counter private (val count: Int)
object Counter {
  def apply(initial: Int): Counter = new Counter(initial)
}

// === partial function ===
val divide: PartialFunction[Int, Int] = {
  case d if d != 0 => 42 / d
}

// === var / val ===
def varVal(): Unit = {
  val immutable = 42
  var mutable = 0
  mutable += 1
}
"""

SOURCES["lua"] = r"""
-- === local variables ===
local x = 1
local y, z = 2, 3
local a, b, c = "hello", true, nil

-- === global variables ===
globalVar = 42

-- === functions ===
local function add(a, b)
    return a + b
end

function greet(name)
    return "Hello, " .. name .. "!"
end

-- === closures ===
local function counter()
    local count = 0
    return function()
        count = count + 1
        return count
    end
end

-- === variadic ===
local function sum(...)
    local args = {...}
    local total = 0
    for _, v in ipairs(args) do
        total = total + v
    end
    return total
end

-- === tables (arrays) ===
local arr = {1, 2, 3, 4, 5}
local mixed = {1, "two", true, nil, {nested = true}}
local empty = {}

-- === tables (dictionaries) ===
local person = {
    name = "Alice",
    age = 30,
    ["full name"] = "Alice Smith",
}

-- === table access ===
local n = person.name
local a = person["age"]
person.email = "alice@example.com"
person["phone"] = "555-0100"

-- === metatables ===
local mt = {
    __index = function(t, k) return "default" end,
    __newindex = function(t, k, v) rawset(t, k, v) end,
    __tostring = function(t) return "table" end,
    __add = function(a, b) return a.val + b.val end,
    __eq = function(a, b) return a.val == b.val end,
}

local obj = setmetatable({val = 10}, mt)

-- === if/elseif/else ===
if x > 0 then
    print("positive")
elseif x == 0 then
    print("zero")
else
    print("negative")
end

-- === while ===
while x > 0 do
    x = x - 1
end

-- === repeat/until ===
repeat
    x = x + 1
until x >= 10

-- === numeric for ===
for i = 1, 10 do
    print(i)
end

for i = 10, 1, -1 do
    print(i)
end

-- === generic for ===
for k, v in pairs(person) do
    print(k, v)
end

for i, v in ipairs(arr) do
    print(i, v)
end

-- === do block (scope) ===
do
    local scoped = "only here"
    print(scoped)
end

-- === multiple return ===
local function divmod(a, b)
    return math.floor(a / b), a % b
end

local q, r = divmod(17, 5)

-- === method calls ===
local str = "hello"
local upper = str:upper()
local sub = str:sub(1, 3)

-- === string concatenation ===
local full = "Hello" .. " " .. "World"

-- === string length ===
local len = #"hello"
local arrLen = #arr

-- === logical operators ===
local result = x and y or z
local notX = not x

-- === comparison ===
local eq = x == y
local neq = x ~= y

-- === pcall / xpcall (error handling) ===
local ok, err = pcall(function()
    error("something went wrong")
end)

local ok2, err2 = xpcall(function()
    error("boom")
end, function(e)
    return "caught: " .. e
end)

-- === coroutines ===
local co = coroutine.create(function(a, b)
    coroutine.yield(a + b)
    coroutine.yield(a * b)
    return a - b
end)

local status, val = coroutine.resume(co, 3, 4)

-- === goto ===
goto continue_label
print("skipped")
::continue_label::

-- === varargs ===
local function printAll(...)
    local args = {...}
    for i = 1, select("#", ...) do
        print(select(i, ...))
    end
end

-- === OOP pattern ===
local Animal = {}
Animal.__index = Animal

function Animal.new(name, sound)
    local self = setmetatable({}, Animal)
    self.name = name
    self.sound = sound
    return self
end

function Animal:speak()
    return self.name .. " says " .. self.sound
end

local dog = Animal.new("Dog", "Woof")
print(dog:speak())
"""

SOURCES["pascal"] = r"""
program AuditSample;

uses SysUtils, Classes;

{ === constants === }
const
  MAX_SIZE = 100;
  PI_APPROX = 3.14159;
  GREETING = 'Hello, World!';

{ === type declarations === }
type
  TColor = (clRed, clGreen, clBlue);
  TPoint = record
    X, Y: Integer;
  end;
  TIntArray = array[0..9] of Integer;
  TDynArray = array of Integer;
  PNode = ^TNode;
  TNode = record
    Value: Integer;
    Next: PNode;
  end;

{ === set type === }
type
  TCharSet = set of Char;

{ === class === }
type
  TAnimal = class
  private
    FName: string;
    FAge: Integer;
  public
    constructor Create(const AName: string; AAge: Integer);
    destructor Destroy; override;
    function GetName: string;
    procedure SetAge(AAge: Integer);
    property Name: string read FName write FName;
    property Age: Integer read FAge write SetAge;
  end;

constructor TAnimal.Create(const AName: string; AAge: Integer);
begin
  inherited Create;
  FName := AName;
  FAge := AAge;
end;

destructor TAnimal.Destroy;
begin
  inherited Destroy;
end;

function TAnimal.GetName: string;
begin
  Result := FName;
end;

procedure TAnimal.SetAge(AAge: Integer);
begin
  if AAge >= 0 then
    FAge := AAge;
end;

{ === interface === }
type
  IPrintable = interface
    procedure Print;
  end;

{ === procedures and functions === }
function Add(A, B: Integer): Integer;
begin
  Result := A + B;
end;

procedure Greet(const Name: string);
begin
  WriteLn('Hello, ', Name, '!');
end;

function Factorial(N: Integer): Integer;
begin
  if N <= 1 then
    Result := 1
  else
    Result := N * Factorial(N - 1);
end;

{ === var parameters === }
procedure Swap(var A, B: Integer);
var
  Temp: Integer;
begin
  Temp := A;
  A := B;
  B := Temp;
end;

{ === control flow === }
procedure ControlFlow;
var
  X, I: Integer;
begin
  X := 10;

  { if/else }
  if X > 5 then
    WriteLn('big')
  else if X > 0 then
    WriteLn('small')
  else
    WriteLn('negative');

  { case/of }
  case X of
    1: WriteLn('one');
    2, 3: WriteLn('two or three');
    4..10: WriteLn('four to ten');
  else
    WriteLn('other');
  end;

  { for loop }
  for I := 1 to 10 do
    WriteLn(I);

  for I := 10 downto 1 do
    WriteLn(I);

  { while }
  while X > 0 do
  begin
    Dec(X);
  end;

  { repeat/until }
  repeat
    Inc(X);
  until X >= 10;
end;

{ === with statement === }
procedure WithStatement;
var
  P: TPoint;
begin
  with P do
  begin
    X := 10;
    Y := 20;
  end;
end;

{ === try/except/finally === }
procedure ErrorHandling;
begin
  try
    try
      raise Exception.Create('oops');
    except
      on E: Exception do
        WriteLn(E.Message);
    end;
  finally
    WriteLn('cleanup');
  end;
end;

{ === arrays === }
procedure ArrayOps;
var
  StaticArr: TIntArray;
  DynArr: TDynArray;
  I: Integer;
begin
  for I := 0 to 9 do
    StaticArr[I] := I * I;

  SetLength(DynArr, 5);
  for I := 0 to High(DynArr) do
    DynArr[I] := I + 1;
end;

{ === string operations === }
procedure StringOps;
var
  S, S2: string;
  C: Char;
begin
  S := 'Hello';
  S2 := S + ' World';
  C := S[1];
  Insert(' dear', S2, 6);
  Delete(S2, 1, 5);
end;

{ === pointer operations === }
procedure PointerOps;
var
  P: ^Integer;
  Node: PNode;
begin
  New(P);
  P^ := 42;
  WriteLn(P^);
  Dispose(P);

  New(Node);
  Node^.Value := 10;
  Node^.Next := nil;
  Dispose(Node);
end;

{ === main program === }
var
  A: TAnimal;
begin
  A := TAnimal.Create('Dog', 5);
  try
    WriteLn(A.Name);
    WriteLn(A.Age);
    A.Age := 6;
  finally
    A.Free;
  end;

  WriteLn(Add(3, 4));
  WriteLn(Factorial(5));

  ControlFlow;
  WithStatement;
  ErrorHandling;
  ArrayOps;
  StringOps;
  PointerOps;
end.
"""

# ---------------------------------------------------------------------------
# Parser name mapping (tree-sitter names)
# ---------------------------------------------------------------------------

TS_LANG_NAMES: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "java": "java",
    "ruby": "ruby",
    "go": "go",
    "php": "php",
    "c_sharp": "csharp",
    "c": "c",
    "cpp": "cpp",
    "rust": "rust",
    "kotlin": "kotlin",
    "scala": "scala",
    "lua": "lua",
    "pascal": "pascal",
}

FRONTEND_LANG_NAMES: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "java": "java",
    "ruby": "ruby",
    "go": "go",
    "php": "php",
    "c_sharp": "csharp",
    "c": "c",
    "cpp": "cpp",
    "rust": "rust",
    "kotlin": "kotlin",
    "scala": "scala",
    "lua": "lua",
    "pascal": "pascal",
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AuditResult:
    """Result of a two-pass audit for one language."""

    language: str
    total_ast_types: int
    handled_count: int
    unhandled_structural: list[str]
    unhandled_substantive: list[str]
    symbolic_unsupported: list[dict]


# ---------------------------------------------------------------------------
# Pass 1 helpers — dispatch table comparison with block-reachability
#
# The key insight: a node type can only produce SYMBOLIC if _lower_stmt
# is called on it, which only happens when _lower_block iterates the
# named children of a "block context" node. Block contexts are:
#   1. The root node (lower() calls _lower_block(root))
#   2. Any node whose type maps to _lower_block in _STMT_DISPATCH
#      (e.g., compound_statement, block, statement_block)
#
# An unhandled node type is a substantive gap ONLY if it appears as a
# direct named child of one of these block contexts. Otherwise, it is
# a deep structural node consumed by the parent's lowerer.
# ---------------------------------------------------------------------------


def collect_ast_types(source: str, ts_language: str) -> set[str]:
    """Parse source and collect all unique named AST node types."""
    parser = tree_sitter_language_pack.get_parser(ts_language)
    tree = parser.parse(source.encode("utf-8"))
    types: set[str] = set()

    def _walk(node):
        if node.is_named:
            types.add(node.type)
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return types


def get_handled_types(frontend) -> set[str]:
    """Union of all dispatch + noise + comment types from a frontend."""
    handled = set(frontend._EXPR_DISPATCH.keys()) | set(frontend._STMT_DISPATCH.keys())
    if hasattr(frontend, "NOISE_TYPES"):
        handled |= frontend.NOISE_TYPES
    if hasattr(frontend, "COMMENT_TYPES"):
        handled |= frontend.COMMENT_TYPES
    return handled


def get_block_types(frontend) -> set[str]:
    """Identify node types whose _STMT_DISPATCH handler is _lower_block.

    These are types like ``compound_statement``, ``block``,
    ``statement_block`` — nodes where _lower_block would iterate children
    rather than delegate to a specific handler.

    Returns the set of type strings that map to _lower_block in the
    frontend's statement dispatch table.
    """
    return {
        node_type
        for node_type, handler in frontend._STMT_DISPATCH.items()
        if getattr(handler, "__func__", None) is BaseFrontend._lower_block
    }


def classify_by_block_reachability(
    source: str,
    ts_language: str,
    unhandled_types: set[str],
    block_types: set[str],
) -> tuple[list[str], list[str]]:
    """Classify unhandled types by whether they are block-reachable.

    Walks the AST and identifies which unhandled node types appear as
    direct named children of block-iterated nodes.

    A block context is a node where ``_lower_block`` would iterate its
    children:
      - The root node (always — lower() calls _lower_block(root))
      - A node whose type is in ``block_types`` (maps to _lower_block
        in _STMT_DISPATCH)

    Returns (structural, substantive) as sorted lists of type names.
    """
    parser = tree_sitter_language_pack.get_parser(ts_language)
    tree = parser.parse(source.encode("utf-8"))
    reachable: set[str] = set()

    def _is_block_context(node, is_root: bool) -> bool:
        """Determine if _lower_block would iterate this node's children.

        Block contexts are nodes where _lower_block is explicitly called:
          - The root node (from lower())
          - Nodes whose type maps to _lower_block in _STMT_DISPATCH
            (e.g., compound_statement, block, statement_block)

        Unhandled nodes are NOT block contexts — they never have
        _lower_block called on them. They pass through _lower_stmt →
        _lower_expr → SYMBOLIC instead.
        """
        if is_root:
            return True
        return node.type in block_types

    def _walk(node, is_root: bool):
        if _is_block_context(node, is_root):
            for child in node.children:
                if child.is_named and child.type in unhandled_types:
                    reachable.add(child.type)
        for child in node.children:
            if child.is_named:
                _walk(child, is_root=False)

    _walk(tree.root_node, is_root=True)

    structural = sorted(unhandled_types - reachable)
    substantive = sorted(reachable)
    return structural, substantive


# ---------------------------------------------------------------------------
# Pass 2 helpers — runtime SYMBOLIC check
# ---------------------------------------------------------------------------


def run_symbolic_check(frontend, source: str, ts_language: str) -> list[dict]:
    """Lower source through frontend and collect unsupported SYMBOLIC entries."""
    parser = tree_sitter_language_pack.get_parser(ts_language)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    instructions = frontend.lower(tree, source_bytes)

    lines = source.split("\n")
    return [
        _extract_symbolic_info(inst, operand, lines)
        for inst in instructions
        if inst.opcode == Opcode.SYMBOLIC
        for operand in inst.operands
        if isinstance(operand, str) and operand.startswith("unsupported:")
    ]


def _extract_symbolic_info(inst, operand: str, lines: list[str]) -> dict:
    """Extract node type and source text from a SYMBOLIC instruction."""
    node_type = operand.replace("unsupported:", "")
    loc = inst.source_location
    src_text = "<unknown>"
    if loc and not loc.is_unknown():
        start_line = loc.start_line - 1
        end_line = loc.end_line - 1
        if 0 <= start_line < len(lines):
            src_text = (
                lines[start_line][loc.start_col : loc.end_col]
                if start_line == end_line
                else lines[start_line][loc.start_col :]
            )
            src_text = src_text.strip()[:80]
    return {"node_type": node_type, "source_text": src_text}


# ---------------------------------------------------------------------------
# Main audit orchestration
# ---------------------------------------------------------------------------


def audit_language(lang_key: str) -> AuditResult:
    """Run two-pass audit for a single language."""
    source = SOURCES[lang_key]
    ts_name = TS_LANG_NAMES[lang_key]
    frontend_name = FRONTEND_LANG_NAMES[lang_key]

    frontend = get_deterministic_frontend(frontend_name)

    # Pass 1: dispatch table comparison with block-reachability
    all_types = collect_ast_types(source, ts_name)
    handled = get_handled_types(frontend)
    unhandled = all_types - handled
    block_types = get_block_types(frontend)
    structural, substantive = classify_by_block_reachability(
        source, ts_name, unhandled, block_types
    )

    # Pass 2: runtime SYMBOLIC check
    symbolic_results = run_symbolic_check(frontend, source, ts_name)

    return AuditResult(
        language=lang_key,
        total_ast_types=len(all_types),
        handled_count=len(handled & all_types),
        unhandled_structural=structural,
        unhandled_substantive=substantive,
        symbolic_unsupported=symbolic_results,
    )


def print_language_result(result: AuditResult):
    """Print detailed audit results for one language."""
    logger.info("")
    logger.info("=== AUDIT: %s ===", result.language)
    logger.info("")

    structural_count = len(result.unhandled_structural)
    substantive_count = len(result.unhandled_substantive)
    unhandled_total = structural_count + substantive_count

    logger.info("Pass 1 -- Dispatch table coverage:")
    logger.info("  AST types found in source:     %3d", result.total_ast_types)
    logger.info("  Handled (dispatch+noise):      %3d", result.handled_count)
    logger.info("  Unhandled:                     %3d", unhandled_total)
    logger.info("    Structural (deep/unreachable): %3d", structural_count)
    logger.info("    Substantive (block-reachable): %3d", substantive_count)

    for gap in result.unhandled_substantive:
        logger.info("      - %s", gap)

    logger.info("")
    logger.info("Pass 2 -- Runtime SYMBOLIC check:")
    logger.info(
        "  SYMBOLIC instructions:         %3d", len(result.symbolic_unsupported)
    )

    for entry in result.symbolic_unsupported:
        logger.info("      - %s  (%s)", entry["node_type"], entry["source_text"])


def main():
    results: list[AuditResult] = []

    for lang_key in TS_LANG_NAMES:
        logger.info("Auditing %s...", lang_key)
        try:
            result = audit_language(lang_key)
            results.append(result)
        except Exception as e:
            logger.error("  ERROR auditing %s: %s", lang_key, e)

    for result in results:
        print_language_result(result)

    # Cross-language summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("  CROSS-LANGUAGE SUMMARY")
    logger.info("=" * 70)
    logger.info("")
    logger.info(
        "  %-15s %5s %5s %5s %5s",
        "Language",
        "AST",
        "Hndl",
        "Gaps",
        "SYMB",
    )
    logger.info("  %s", "-" * 45)

    total_gaps = 0
    total_symbolic = 0

    for r in results:
        gap_count = len(r.unhandled_substantive)
        sym_count = len(r.symbolic_unsupported)
        total_gaps += gap_count
        total_symbolic += sym_count
        logger.info(
            "  %-15s %5d %5d %5d %5d",
            r.language,
            r.total_ast_types,
            r.handled_count,
            gap_count,
            sym_count,
        )

    logger.info("  %s", "-" * 45)
    logger.info(
        "  %-15s %5s %5s %5d %5d",
        "TOTAL",
        "",
        "",
        total_gaps,
        total_symbolic,
    )

    if total_gaps > 0:
        logger.info("")
        logger.info("  Languages with substantive gaps:")
        for r in results:
            if r.unhandled_substantive:
                logger.info(
                    "    %s: %s",
                    r.language,
                    ", ".join(r.unhandled_substantive),
                )

    if total_symbolic > 0:
        logger.info("")
        logger.info("  Languages with runtime SYMBOLIC issues:")
        for r in results:
            if r.symbolic_unsupported:
                types = sorted({e["node_type"] for e in r.symbolic_unsupported})
                logger.info("    %s: %s", r.language, ", ".join(types))


if __name__ == "__main__":
    main()
