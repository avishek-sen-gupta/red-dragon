# HLASM Frontend

> `interpreter/hlasm/hlasm_frontend.py` · Extends `Frontend` directly

## Overview

The HLASM frontend lowers an IBM High Level Assembler program to IR. Parsing and
assembly are the che4z language server's, through a forked bridge executable;
Python lowers what che4z has already resolved. The machine claims z17 problem
state and stays in AMODE 31. Lowered so far: SVC and the load and store, load
address and immediates, signed add and subtract, logical add and subtract, compare,
compare and branch or trap, boolean, shift and rotate, multiply and divide, storage move, storage compare, translate, branch on condition, branch and link, branch on count and index, execute, conditional load and store, select and bit count, interlocked-update, Unicode conversion and string search, high-word, miscellaneous, packed-decimal arithmetic, packed-decimal compare and test, decimal conversion and edit units (see
Opcode Units).
Any other opcode abends `S0C1` at run time.

## Architecture

```
HLASM source
  │
  ▼
hlasm_ast_bridge (che4z fork, C++ subprocess)
  │  assembles the source with its SYSLIB; writes the program as JSON
  │  exit 2 with diagnostics on any E/S diagnostic
  ▼
hlasm_asg (leaf package)
  │  HlasmBridgeParser — runs the bridge, reads JSON into HlasmProgram (Pydantic)
  ▼
HlasmFrontend
  │  lower():         one IR function per module, entered by dispatching on a target address,
  │                   then the IR functions its statements call (the DPD codec)
  │  object_module:   ESD, TXT, RLD and END for the binder
  ▼
compile_hlasm / link_hlasm_units (interpreter/project/hlasm_compile.py)
  │  AST file → unit file per assembly → linked image
  ▼
bind_image (interpreter/hlasm/image_binding.py)
     start-up module: machine state, one region per module, commons, stubs, TXT, RLD;
     job-step module: one function per SD/LD name (ProgramEntry(<name>)) and per module's END
```

che4z supplies symbol values, lengths, location counters and USING resolution.
Python computes only DC/DS byte images, section placement and runtime effective
addresses.

## Module Map

| Module | Purpose |
|---|---|
| `hlasm_asg/hlasm_bridge_parser.py` | `make_hlasm_parser(syslib)`, `HlasmBridgeParser`; exit 2 → `HlasmParseError`, other failures → `HlasmBridgeFailure`. The default bridge path is resolved from the package, not the working directory; `HLASM_AST_BRIDGE` overrides it, and a bare name there is looked up on `PATH`. A bridge that cannot be found raises `HlasmBridgeNotFound`; a SYSLIB directory that does not exist raises `MissingSyslibDirectory`, from `compile_hlasm` and from `run(copybook_dirs=...)` alike. `identity` is the SHA-256 of the bridge binary |
| `hlasm_asg/assembly_input.py`, `assembly_inputs.py` | `AssemblyInput` (SYSPARM, SYSJOB, SYSSTEP, SYSIN_DSN, SYSIN_MEMBER); `AssemblyInputs`: the values one assembly is given and the instant it reads |
| `interpreter/hlasm/assembly_diagnostics.py` | The unit's diagnostics below error level (che4z warnings and MNOTEs, DC conversion warnings) as `UnitDiagnostic`s |
| `interpreter/project/hlasm_compile_options.py` | `HlasmCompileOptions(names, clock)`: the inputs `compile_hlasm` takes; `clock` is an `AssemblyClock` (`hlasm_asg/assembly_clock.py`; COBOL's `CompileClock`, which the import contracts keep from `interpreter.project`), `SystemAssemblyClock` by default |
| `interpreter/frontends/__init__.py` | `get_hlasm_parser(syslib)`: the bridge parser with `hlasm-bridge/maclib/` first on SYSLIB |
| `hlasm-bridge/maclib/` | Our macros: `WTO`, `ABEND`, `SAVE`, `RETURN`, `YREGS`, `GETMAIN`, `FREEMAIN`, `STORAGE`, `TIME`, `DCB`, `DCBD`, `OPEN`, `CLOSE`, `GET`, `PUT`, and their `RD*` helpers |
| `hlasm_asg/program/` | The bridge JSON models, one class per file. A D(X,B) storage operand also carries its address as written (`written`): the section and offset of an implicit address, before USING resolution, or the absolute displacement. Each DC/DS operand carries its offset and bit offset from che4z's location counter, its length unit (bytes, or bits for `L.n`), scale and exponent. `*` is the address of each constant: an address operand that names the location counter is exported per duplication copy (`ADDRESSES_PER_COPY`), each value evaluated at its own address. An S-constant is a base and displacement resolved through USING. `DC 0F` has an `OMITTED` nominal. CCW, CCW0 and CCW1 are statements with their command code, address, flags and count. Each literal carries the origin of the statement that first used it, a CCW's literals included. The program lists AMODE and RMODE statements, and each diagnostic its macro call stack (`related`) |
| `interpreter/hlasm/hlasm_frontend.py` | `HlasmFrontend(program, module)`: `lower()`, `object_module`, `entry_name`, `entry_label` |
| `interpreter/hlasm/machine.py` | GPR region (`__hlasm_gprs`, 8 bytes per register), `__hlasm_cc`, `__hlasm_pm`, `__hlasm_tod_last` (the last STCK value); the access-register region (`__hlasm_ars`, 4 bytes per register, all 0); the vector-register region (`__hlasm_vrs`, 16 bytes per register, all 0) and `__hlasm_fpc`, allocated after the sections so their addresses do not move |
| `interpreter/hlasm/floating_point_constant.py`, `float_nominal.py` | E, D and L images, built at assembly time by `zarch_float`'s packers (Language Reference SC26-4940-09, pp. 148-158). `parse_float_nominal` turns each value into a `FloatNumber` (sign, coefficient, written exponent with the modifier, rounding mode) or a `FloatSpecial` once. No extension: HFP rounded by adding one in the first lost bit; a positive zero; the scale modifier shifts the fraction right; a length modifier keeps the leftmost bytes or bits, rounded. Out of range raises `DcCharacteristicOutOfRange` (ASMA064S); a scale or length that leaves no fraction, or cuts the characteristic, raises `DcPrecisionLost` (ASMA073E). H and Q: rounding modes R1 (default), R4-R7, a signed zero, overflow to the largest magnitude, underflow denormalized or zero, and (MAX), (MIN), (DMIN). B: IEEE conversion under R4 (default), R1, R5-R7, into any length from 9/12/16 bits; overflow gives infinity or Nmax by mode; all seven special values, (INF) and the NaNs needing 11/14/18 bits (`DcLengthWrong`, ASMA068S: the manual gives the minimum, and ASMA068S is its message for a wrong length modifier). With one bit of precision a tie has no even significand; round to nearest even then takes the even image (biased exponent), our ruling. D: the written coefficient and exponent fitted under R8 (default) to R15, so an exact value keeps its quantum (IEEE 754-2008 conversion; the manual does not say). (NAN) and (QNAN) are the same quiet NaN. (MIN) is 1E-95/-383/-6143, the smallest normal number, and (DMIN) the smallest subnormal (ruling R60: p. 158 defines MIN only for BFP and HFP). LQ converts as LH. Exponents beyond ±20000 are clamped: every format overflows or underflows alike past them. With a type extension each value carries at most one `DcWarning` (overflow, then underflow, then inexact) on its `ConstantImage` or `BitLengthImage`, as pp. 127 and 156-157 warn; H saturation counts as overflow and denormalization as underflow. They are logged and kept in the unit file (see Diagnostics). Unextended HFP raises none |
| `interpreter/hlasm/storage_layout.py` | Each section's DC and literal pieces at their offsets: constant images, address slots and external slots |
| `interpreter/hlasm/binder.py`, `binder_start_up.py`, `job_step.py`, `image_binding.py`, `far_branch.py`, `unresolved_call.py` | The binder and the far branch (see Binder, Control Across Modules) |
| `interpreter/hlasm/cobol_linkage.py`, `cobol_program.py`, `cobol_owner.py` | Calls between COBOL and HLASM (see COBOL Linkage) |
| `interpreter/hlasm/program_services.py` | SVC 6, 8 and 9: LINK, LOAD, DELETE |
| `interpreter/hlasm/program_entry.py` | `__entry_<NAME>`, the variable COBOL's CALL shares, with the name uppercased: `program_entry_name(name)` at lowering time, `emit_program_entry_name` in IR for LINK's run-time name |
| `interpreter/hlasm/data_set_services.py` | SVC 19, 20, 200 and 201: OPEN, CLOSE, GET, PUT over the record provider (`interpreter.record_io`) |
| `interpreter/hlasm_run_inputs/` | The HLASM run inputs, a sibling of `interpreter.hlasm` so `run()` can import it (the import contracts keep `interpreter.run` from `interpreter.hlasm`): `run_input_names.py` (builtin names, PARM area sizes, the positions of `__hlasm_dd`'s facts), `run_input_builtins.py` (`run_input_builtins(clock, parm)`; `unsupplied_run_input_builtins()`, the host clock, an empty PARM and no DD definitions, which `run()` adds under any builtins it is given) |
| `interpreter/hlasm_run_inputs/dd_definition.py`, `record_format.py`, `dd_builtins.py`, `dd_run_inputs.py` | `DdDefinition(path, recfm, lrecl, blksize)`, one per DDNAME; `dd_builtins(dds)`: `__hlasm_dd(name)` answers `[1, RECFM byte, LRECL, BLKSIZE]`, 0 where not given, or zeros for a DDNAME not supplied; `dd_run_inputs(dds)` returns that builtin and the `RunInputs` whose `path_overrides` send each DDNAME to its DD's path, for the caller's file provider |
| `interpreter/hlasm_run_inputs/declare_file_builtins.py` | `declare_file_builtins()`: `__hlasm_declare_file(ddname, variable, record_length)` declares the provider's sequential `FileFrame` for OPEN. It imports `interpreter.record_io`, not `interpreter.cobol`; callers compose it |
| `interpreter/hlasm_run_inputs/job_parm_builtins.py` | `job_parm_builtins(parm)`: the job-step PARM, a run input of at most 100 characters (`ParmTooLong`), as a halfword length and EBCDIC text through `EbcdicTable`; a character it has no code for raises `ParmNotEncodable` |
| `interpreter/hlasm/dc_encoding.py` | DC images: C, CA, CE, CU, X, B, F, FD, H, P, Z, A, AD, Y, V, VD, S, SY, Q, QD, J, JD (Q and J as binder slots, filled at bind), and E, D, L with their extensions through `floating_point_constant.py`. Each operand is placed at the offset che4z exported; Python has no alignment table of its own, and alignment bytes inside a DC are zero. F, FD and H take fractions, a written exponent, the exponent and scale modifiers and the U prefix, and the scaled value is rounded to a whole number. A negative value rounds on its magnitude (-1.5 is -2); that is our reading of the Language Reference, which does not say. A written exponent that, with the exponent modifier, falls outside -85 to +75 raises `DcExponentOutOfRange` (ASMA071E) before any arithmetic. A value outside its length raises `DcValueOutOfRange` with the statement's line (ASMA072E); a literal gives the line that first used it. Y accepts -32768 to 65535 (a halfword read as signed or unsigned) and refuses anything else the same way, while A truncates at the left as IBM specifies. An S-constant in a literal resolves through the USING in force where its pool is assembled, whichever LOCTR the pool lands in. `*` in a literal is the instruction's address in every copy. Bit-length operands (`L.n`) pack from che4z's bit offset, each value in the next free bits (C, E, D and L from their high-order end, other types from the low-order end) and the last byte zero-filled. CCW and CCW0 are format-0 channel command words (24-bit address), CCW1 format 1 (31-bit); a relocatable or external data address is an RLD like an A-constant |
| `interpreter/hlasm/entry_state.py` | Entry resolution and entry registers (R14 = `0xFF0` return sentinel, R13 = 72-byte save area, R15 = entry address, R1 = parameter list), set by the job step |
| `interpreter/hlasm/branch_dispatch.py` | The module function's activation and `hl_dispatch`: returns at R14, maps an address in the module to a statement label, hands any other to the far branch (see Control Across Modules) |
| `interpreter/hlasm/operands.py` | `reg_operand`, `mask_operand`, `optional_mask_operand`, `imm_operand`, `value_operand` (R, M or I), `storage_operand`, `reloc_operand`, `storage_length_operand`, `vec_reg_operand`, `vector_indexed_operand` (D(V,B), its own type), `optional_imm_operand`: typed operand access; a mismatch raises `HlasmLoweringError`. `statement_place` names a statement in messages |
| `interpreter/hlasm/hlasm_lowering_error.py` | `HlasmLoweringError`: names the statement (mnemonic, section, offset, operand) and what was found |
| `interpreter/hlasm/opcodes/svc.py` | SVC, by number, written or set by EX |
| `interpreter/hlasm/opcodes/load_store.py` | The load and store unit |
| `interpreter/hlasm/opcodes/load_address_immediate.py` | The load address and immediates unit |
| `interpreter/hlasm/opcodes/signed_add_subtract.py` | The signed add and subtract unit |
| `interpreter/hlasm/opcodes/logical_add_subtract.py` | The logical add and subtract unit |
| `interpreter/hlasm/opcodes/compare.py` | The compare unit, signed and logical |
| `interpreter/hlasm/opcodes/compare_branch_trap.py` | The compare-and-branch, compare-and-trap and load-and-trap unit |
| `interpreter/hlasm/conditional.py` | `emit_when`: IR that runs only when a condition register is true; `emit_either` picks one of two blocks; `pick` selects one of two values without a branch |
| `interpreter/hlasm/opcodes/boolean.py` | The boolean unit: AND, OR, exclusive OR and the complemented connectives |
| `interpreter/hlasm/opcodes/shift_rotate.py` | The shift and rotate unit, the RISBG family included |
| `interpreter/hlasm/opcodes/multiply_divide.py` | The multiply and divide unit |
| `interpreter/hlasm/opcodes/load_sign.py` | The load and test, complement, positive and negative unit |
| `interpreter/hlasm/opcodes/conditional_select_count.py` | The load and store on condition, select, population and bit count unit |
| `interpreter/hlasm/bit_counts.py` | Branch-free 64-bit counts: population per byte and in total, the right smear, leading and trailing zeros, the lowest and leftmost one bits |
| `interpreter/hlasm/mask_bit_loop.py` | BEXTG and BDEPG: one IR loop over the mask's one bits |
| `interpreter/hlasm/opcodes/under_mask.py` | The test under mask unit |
| `interpreter/hlasm/opcodes/even_odd.py` | An odd register of an even-odd pair form abends `S0C6` before any register is read; R1 by default, or the operands named |
| `interpreter/hlasm/opcodes/ss_move.py` | The storage-to-storage and storage-immediate move unit |
| `interpreter/hlasm/long_move.py` | MVCL, MVCLE, MVCLU: move, then pad, in one execution |
| `interpreter/hlasm/long_operands.py` | `LongOperands`: a long move's or compare's addresses, lengths and shorter length, read before any store |
| `interpreter/hlasm/long_registers.py` | The long forms' register pairs: lengths, both pads (as ints), the even-length checks, the address store and advance, the length count-down |
| `interpreter/hlasm/move_string.py` | MVST |
| `interpreter/hlasm/opcodes/ss_compare.py` | The storage compare unit; CLC |
| `interpreter/hlasm/long_compare.py` | CLCL, CLCLE, CLCLU |
| `interpreter/hlasm/long_spans.py` | Walks two long operands a unit at a time: the common units, then the longer tail against the pad |
| `interpreter/hlasm/compare_string.py` | CLST |
| `interpreter/hlasm/compare_substring.py` | CUSE |
| `interpreter/hlasm/ending_character.py` | The GR0 character of MVST, CLST, SRST (one byte) and SRSTU (two bytes) and its `S0C6` check |
| `interpreter/hlasm/compare_cc.py` | The storage compares' and translates' CCs: a constant CC on a branch; one CC for a loop run to its end, another for a branch out; CC 1 or 2 from two unequal unit values |
| `interpreter/hlasm/unit_value.py` | The unsigned value of a 1- or 2-byte unit, from its image or at a register offset; compares run on ints, never on byte images |
| `interpreter/hlasm/opcodes/translate.py` | The translate unit; TR, TRT, TRTR |
| `interpreter/hlasm/translate_extended.py` | TRE |
| `interpreter/hlasm/translate_characters.py` | TROO, TROT, TRTO, TRTT |
| `interpreter/hlasm/translate_and_test_extended.py` | TRTE, TRTRE |
| `interpreter/hlasm/translation_table.py` | A byte translated through a table, the GR1 table address (bits 61-63 ignored), offsets rescaled between unit widths |
| `interpreter/hlasm/specification_check.py` | A runtime condition abends `S0C6` |
| `interpreter/hlasm/operand_overlap.py` | Whether a destination starts inside the participating source bytes: MVC's byte-loop test and MVCL's destructive overlap |
| `interpreter/hlasm/opcodes/branch_on_condition.py` | The branch on condition unit; `mask_selects`, the mask bit `8 >> CC` |
| `interpreter/hlasm/opcodes/branch_and_link.py` | The branch and link unit and the addressing-mode instructions |
| `interpreter/hlasm/opcodes/loop_branch.py` | The branch on count and branch on index unit |
| `interpreter/hlasm/opcodes/high_word.py` | The high-word unit |
| `interpreter/hlasm/opcodes/miscellaneous.py` | The miscellaneous unit: access registers, LCBB (its `block_count` also serves VLBB), MC, hints, traps |
| `interpreter/hlasm/opcodes/floating_point_support.py` | The floating-point-support unit: FPR moves, sign forms, the FPC, its checks and the simulated-IEEE trap; `emit_vector_exception` (VXC to the DXC byte, `S0DB`) |
| `interpreter/hlasm/element_size.py`, `vector_elements.py` | `ElementSize` (ES 0-4); vector elements by static index and by run-time index modulo the element count |
| `interpreter/hlasm/element_return_field.py` | The fields of an element function's one return value: result, CC, FPC flags, VXC, trap |
| `interpreter/hlasm/opcodes/vector_fields.py` | `m_field` (omitted is 0); element-size, must-be-zero and static-index checks that abend `S0C6` at lowering; a VR operand as a source, V1 as a sink, element replication; the borrow compare, the CC from an element count, and the call of an element function whose CC is set only with CS |
| `interpreter/hlasm/opcodes/vector_memory.py` | The vector loads and stores: whole registers and ranges, elements, immediates, replicated and zero-extended elements, VLL, VSTL, VLBB, gather and scatter, the byte- and element-reversed forms; `element_placement.py` holds a zero-extended element's width and shift |
| `interpreter/hlasm/opcodes/vector_logical_compare.py` | The vector integer bitwise forms and VEVAL, element compares (VCEQ, VCH, VCHL as element functions), VEC, VECL, VTM, minimum and maximum, complement and absolute value, population and leading and trailing zero counts |
| `interpreter/hlasm/opcodes/vector_integer_arithmetic.py` | The vector integer add, subtract and their carries, averages, multiplies (high, low, even, odd, multiply-and-add, VMSL), Galois-field multiply, checksum and sums across, and the divides as element functions with the integer-divide exception |
| `interpreter/hlasm/opcodes/vector_register.py` | The vector register manipulations: generated masks, elements to and from GPRs, merges, permutes, packs (the saturating ones as element functions), replication, selection, sign extension, unpacks |
| `interpreter/hlasm/opcodes/bfp_arithmetic.py` | The BFP arithmetic unit's builtin forms: add, subtract, multiply, divide, square root, fused, load FP integer, divide to integer |
| `interpreter/hlasm/opcodes/bfp_class.py` | BFP COMPARE, COMPARE AND SIGNAL and TEST DATA CLASS, in IR (ruling R44) |
| `interpreter/hlasm/opcodes/bfp_sign.py` | BFP LOAD AND TEST and the sign forms, in IR |
| `interpreter/hlasm/opcodes/bfp_conversion.py` | BFP conversions: to fixed and logical, rounding from fixed and LOAD ROUNDED through builtins; exact from fixed and lengthening in IR (red-dragon-6uyp.52) |
| `interpreter/hlasm/opcodes/bfp_forms.py` | Statement-level BFP parts: the M3 modifier and its check, image stores after delivery, a BFP builtin call |
| `interpreter/hlasm/opcodes/fp_forms.py` | Statement-level parts BFP and DFP share: one builtin call through the ladder, suppressed bits, the specification check, GR and rounded-image stores |
| `interpreter/hlasm/opcodes/bfp_ir.py` | BFP image IR: field lists, encoding, an image's CC, the BFP rounding mode |
| `interpreter/hlasm/opcodes/fp_ir.py`, `interpreter/hlasm/ieee_outcome.py`, `interpreter/hlasm/fp_slots.py` | IR both IEEE radixes share: result fields, FPC mode codes, the result-list slots and FPC bits, and the IEEE trap ladder over an `IeeeOutcome` |
| `interpreter/hlasm/opcodes/hfp_arithmetic.py` | The HFP arithmetic unit's builtin forms: add, subtract, compare, multiply, divide, halve, square root, load FP integer, the multiply-and-add forms (red-dragon-6uyp.53) |
| `interpreter/hlasm/opcodes/hfp_sign.py` | HFP LOAD AND TEST and the sign forms, in IR |
| `interpreter/hlasm/opcodes/hfp_ir.py` | HFP image IR: field lists, normalized fields of a binary value, encoding with the extended low-order part, an image's CC, and the program-mask ladder |
| `interpreter/hlasm/opcodes/hfp_conversion.py` | HFP conversions: to fixed and to BFP through builtins; from fixed, from BFP, load lengthened and load rounded in IR (red-dragon-6uyp.54) |
| `interpreter/hlasm/opcodes/dfp_codec.py`, `dpd_lanes.py`, `interpreter/hlasm/dfp_layout.py` | DFP images to `[negative, e, significand]` and back as IR functions, one per format (ruling R49); `e` is the biased exponent or -1/-2/-3 for infinity, QNaN, SNaN. All declets decode or encode at once, ten bits per lane |
| `interpreter/hlasm/opcodes/pfpo.py`, `pfpo_codec.py`, `interpreter/hlasm/pfpo_builtins.py`, `pfpo_formats.py` | PFPO: GR0 decoded and checked, format dispatches around the `__hlasm_pfpo` builtin, the return code and alternate action (red-dragon-6uyp.56) |
| `interpreter/hlasm/opcodes/dfp_decimal.py`, `decimal_lanes.py` | DFP to and from signed packed, unsigned packed and zoned decimal in IR, over decimal lanes (red-dragon-6uyp.56) |
| `interpreter/hlasm/opcodes/dfp_conversion.py` | DFP conversions: to and from fixed and logical and LOAD ROUNDED through builtins; LOAD LENGTHENED in IR (red-dragon-6uyp.56) |
| `interpreter/hlasm/ir_function.py`, `program_function.py` | An IR function called by name; the call records it on the emitter, and the frontend defines each recorded function once after the entry function, repeating until no body calls an undefined one |
| `interpreter/hlasm/opcodes/fpr_images.py`, `interpreter/hlasm/fpr_layout.py` | Floating-point images of any radix: FPR access by width (short high word, long, pair), FPR and storage operand sources, result-list items |
| `interpreter/hlasm/program_status.py` | SPM, IPM, EPSW |
| `interpreter/hlasm/checksum.py` | CKSM |
| `interpreter/hlasm/clock_instructions.py` | STCK, STCKF, STCKE, ECTG |
| `interpreter/hlasm_run_inputs/machine_clock.py`, `clock_builtins.py` | `MachineClock` (TOD clock, CPU timer); `clock_builtins(clock)`, the `__hlasm_tod_clock` and `__hlasm_cpu_timer` builtins over it |
| `interpreter/hlasm/integer_outcome.py` | A fixed-point conversion builtin's result list: the integer image, the IEEE words and the CC (3 when invalid, else the source's sign); shared by the BFP and DFP builtins |
| `interpreter/hlasm/bfp_builtins.py`, `bfp_fields.py`, `bfp_layout.py`, `bfp_operation.py` | `bfp_builtins()`, one `__hlasm_bfp_<operation>_<format>` builtin per operation and format over `zarch_float`; operands arrive as `[sign, biased exponent, fraction]` lists and results leave as fields plus the trap, flag and DXC bits (ruling R43) |
| `interpreter/hlasm/hfp_builtins.py`, `hfp_layout.py`, `hfp_operation.py`, `hfp_slots.py` | `hfp_builtins()`, one `__hlasm_hfp_<operation>_<format>` builtin per operation and source format over `zarch_float`; operands arrive as `[sign, characteristic, fraction]` lists and results leave as the same fields, characteristic modulo 128, plus condition bits (ruling R46); the conversions take M3 first and return `[image, cc]` (to fixed) or BFP fields and the CC (to BFP) |
| `interpreter/hlasm/dfp_builtins.py`, `dfp_fields.py`, `dfp_operation.py`, `ieee_words.py` | `dfp_builtins()`, one `__hlasm_dfp_<operation>_<format>` builtin per operation and format over `zarch_float`; operands arrive as `[negative, e, significand]` lists and results leave in the BFP result-list layout, the quantum condition as FPC bit X'04' (ruling R49) |
| `interpreter/hlasm_run_inputs/system_machine_clock.py` | `SystemMachineClock`, the host clock over injected wall and process-CPU nanosecond readings: TOD from wall time since 1900-01-01 UTC (no leap seconds), CPU timer down from 2^63 - 1 at 4096 units per microsecond |
| `interpreter/hlasm/cpu_attributes.py` | ECAG's constant attributes |
| `interpreter/hlasm/facility_list.py` | STFLE's constant facility list |
| `interpreter/hlasm/register_part.py`, `register_parts.py` | `RegisterPart`: the low word, high word or whole register, or an access register, that a lowering reads and writes, and `merge` for bytes under a mask |
| `interpreter/hlasm/lower_statement.py` | Lowers one statement: EX and EXRL through `execute.py`, any other machine instruction through `OPCODE_LOWERINGS` |
| `interpreter/hlasm/machine_statements.py` | `MachineStatements`: the assembly's machine statements by section and offset |
| `interpreter/hlasm/execute.py` | EX and EXRL: resolve the target, check it; lower a data-field target once with byte 1 computed in IR, any other target as one inline copy per byte-1 value |
| `interpreter/hlasm/data_field.py`, `written_field.py`, `executed_field.py` | `DataField`: a byte-1 data field (SS length code, SI immediate, SVC number) as a lowering sees it. `WrittenField` is the assembled byte: block region reads and writes, a compile-time dispatch. `ExecutedField` is EX's register: one block per set bit of the length, a chain of equality tests |
| `interpreter/hlasm/field_lowering.py` | `FieldLowering(layout, lower)`: a lowering given its data field; `written_lowerings` adapts them for `OPCODE_LOWERINGS` with `WrittenField`; `with_field_source` turns the field into a `Source` |
| `interpreter/hlasm/byte_one_layouts.py` | Byte 1 of each instruction format, by format and operand shape (`operand_slot.py`); an unlisted shape is an opcode byte. Names the data-field layouts: `LENGTH_BYTE`, `LENGTH_NIBBLES`, `LENGTH_HIGH_NIBBLE`, `LENGTH_AND_IMMEDIATE`, `IMMEDIATE_BYTE`, `NUMBER_BYTE` |
| `interpreter/hlasm/byte_one_layout.py`, `byte_one_field.py` | A format's byte-1 fields, ignored bits and opcode bits; the byte a statement encodes, the values R1 can make of it, the statement a value decodes to |
| `interpreter/hlasm/byte_one_part.py`, `operand_value_part.py`, `storage_index_part.py`, `length_code_part.py` | What a byte-1 field holds: an R, M or I value, an X2 index, or a length code (written length minus one) |
| `interpreter/hlasm/opcodes/operand_sources.py` | Named second-operand sources shared by the arithmetic, compare, compare-and-branch and load-sign units |
| `interpreter/hlasm/opcodes/result_and_cc.py` | Splices a (result, CC) builder over register, storage or immediate operands and stores both; its storage-immediate read-modify-write |
| `interpreter/hlasm/data_movement.py` | `move(source, transforms, sink)`: storage, relative-long, address, immediate and register sources and sinks, addressed by operand index; sign extension, `MOD 2^n` wrap, masks, shifts, byte reversal, bit fields (`field_of`, `into_field`); the even-odd pair's low words as one 64-bit value, or both registers as one 128-bit value; R1+1 as a source; high words as a source and a sink; the storage-immediate read-modify-write |
| `interpreter/hlasm/effective_address.py` | `effective_address` (D(X,B), AMODE 31), `length_operand_address` (D(L,B)), `indexed_address` (index scaled by the element size), `vector_indexed_address` (D(V,B), a vector element as index), `relative_address` (RELOC_IMM) |
| `interpreter/hlasm/alignment_check.py` | An operand off its boundary abends `S0C6` |
| `interpreter/hlasm/fixed_point_overflow.py` | CC 3 with program-mask bit `1000` on abends `S0C8` |
| `interpreter/hlasm/fixed_point_divide.py` | A raised divide condition abends `S0C9`; no mask applies |
| `interpreter/hlasm/write_to_operator.py` | SVC 35 in IR |
| `interpreter/hlasm/byte_loop.py` | An IR loop over offsets from a start to a bound by a fixed step, the offset in `__hlasm_ss_at`, its constants set before the loop; `emit_scan_loop`, whose body may branch out and returns its registers; `emit_byte_loop` from 0 to a length register; `copy_byte`, `copied_byte`, `advance` |
| `interpreter/hlasm/register_span.py` | `RegisterSpan`: the bit positions a RISBG-family field selects within (whole register, high word, low word) and the wrapping range mask |
| `interpreter/hlasm/boolean_connective.py` | A bitwise connective: the binop and whether the right operand or the result is complemented; the eight connectives |
| `interpreter/hlasm/abend_completion.py` | SVC 13 in IR |
| `interpreter/hlasm/storage_services.py`, `storage_request.py` | SVC 10 and SVC 120 in IR over the allocation table |
| `interpreter/hlasm/time_service.py` | SVC 11 in IR: `time_words` turns a TOD value into the DEC, BIN and date words |
| `interpreter/hlasm/statement_location.py` | Each statement's source line, set on the IR it lowers to |
| `interpreter/hlasm/fixed_width_ir.py` | Fixed-width signed add/subtract/multiply, load-and-test, complement, absolute and negative-absolute and logical add/subtract with carry-in, bitwise connectives, logical and signed shifts and rotates, each with its condition code, the sign CC (0 zero, 1 leftmost bit one, 2 other), and division truncating toward zero, built in IR |
| `interpreter/hlasm/inline_ir.py` | Splices a builder's IR under fresh registers; `inline_pair` splits a returned pair, such as (result, CC) |
| `interpreter/hlasm/hlasm_emitter.py` | `HlasmEmitter`: the lowering's instruction sink; `load_ar` and `store_ar` for access registers; `load_fpr`, `store_fpr` and their high-word forms for FPRs; `load_field`, `masked_address` (31-bit) and `aligned_region(length, alignment)` for the system services; an immutable cons-list (`chain_link.py`, `empty_chain.py`) flattened once by `instructions()`, so emission is O(n); `locate_from` records a `LocatedSpan` applied at that flatten |
| `interpreter/hlasm/abend.py` | Stores the code in `__hlasm_abend`, then `Halt_` |
| `interpreter/hlasm/opcodes/interlocked.py` | The interlocked-update unit |
| `interpreter/hlasm/place.py`, `places.py` | `Place`: how one lowering reads and replaces an operand; a register's low word or whole value, an even-odd pair joined into one value, storage at an address, storage at an address held in a doubleword (bits 33-63, boundary checked), a register numbered at run time |
| `interpreter/hlasm/comparison.py`, `compare_chain.py` | Interlocked compares in order: the first unequal one replaces its place with the operand and leaves, otherwise the equal path runs; `emit_compare_or_refresh` adds CC 0 or 1 |
| `interpreter/hlasm/compare_swap_store.py` | CSST |
| `interpreter/hlasm/perform_locked_operation.py` | PLO: GR0 checks, the test bit, the function-code tree |
| `interpreter/hlasm/locked_operation.py`, `locked_operations.py`, `plo_frame.py` | A PLO function code as data (`Spot`s resolved against R1 and R3 numbers, the D2 and D4 addresses and the checked list addresses) and the table of codes 0-61 |
| `interpreter/hlasm/value_tree.py` | `emit_value_switch`: one block per run-time value under a tree of `<` tests, then a join; EX, CSST, PLO |
| `interpreter/hlasm/opcodes/unicode_string_search.py` | The Unicode conversion and string search unit |
| `interpreter/hlasm/search_string.py` | SRST, SRSTU |
| `interpreter/hlasm/unicode_conversion.py` | CU12, CU14, CU21, CU24, CU41, CU42 (CUTFU, CUUTF): the step loop, CCs and register updates |
| `interpreter/hlasm/unicode_decoders.py`, `unicode_encoders.py` | UTF-8, UTF-16 and UTF-32 readers (code point, exhaustion, well-formedness) and writers (room check, store) |
| `interpreter/hlasm/conversion_cursor.py`, `conversion_labels.py` | A conversion step's offsets and its exits |
| `interpreter/hlasm/opcodes/packed_arithmetic.py` | The packed-decimal arithmetic unit |
| `interpreter/hlasm/opcodes/packed_compare_test.py` | The packed-decimal compare and test unit |
| `interpreter/hlasm/packed_decimal.py`, `packed_value.py`, `packed_field.py`, `packed_digit_reader.py`, `packed_byte_sink.py` | A signed-packed field (address, run-time length) read into a magnitude, a negative bit, a bad-digit bit and a bad-sign bit; stored right to left with sign C or D; the overflow test and CC by int compares |
| `interpreter/hlasm/packed_operands.py` | The packed operands as fields with L1 (and SS-b's L2) from byte 1, read and checked together |
| `interpreter/hlasm/decimal_exceptions.py` | `S0C7` (DXC 00 in the FPC) and `S0CB` before any store; `S0CA` after the store when program-mask bit `0100` is on |
| `interpreter/hlasm/opcodes/decimal_conversion.py` | The decimal conversion unit |
| `interpreter/hlasm/decimal_packing.py`, `digit_source.py`, `character_field.py` | Pack digits into a signed-packed field and unpack them into zoned, ASCII or Unicode characters, right to left one result unit at a time, each source byte fetched once; bytes left of the source read as zero |
| `interpreter/hlasm/opcodes/edit.py`, `edit_operands.py` | The edit unit: pattern and source addresses, the byte reader and the fill byte |
| `interpreter/hlasm/range_dispatch.py`, `bit_fields.py` | Branch on ascending bounds; masked, shifted and ORed bit fields |

## Compilation Units

One assembly is one unit. `compile_hlasm(source, *, parser, options, work_dir, programs=())`
writes these files to the work directory, each skipped when it already exists:

| File | Holds |
|---|---|
| `<stem>-<digest>.ast.json` | The bridge's program JSON, per assembly |
| `<stem>-<digest>.unit.json` | The lowered `ModuleUnit`; `program` is the END entry name |
| `hlasm-image-<digest>.linked.json` | The image: start-up module, the units, the job-step module |

The main source is `__main__.asm`; each of `programs` keeps its own path.
`link_hlasm_units(units, work_dir)` links unit files already lowered. A second compile of
unchanged source reuses every file.

`<digest>` (`HlasmLoweringSettings`) covers the source bytes, the SYSLIB directories,
the contents of every file in them, the bridge binary's hash and the supplied
`names`. Editing a macro or rebuilding the bridge therefore gets new files. The clock
is not in the digest: a reused unit keeps the time it was assembled at, as COBOL's
`WHEN-COMPILED` does. `lower_hlasm_program(program: SourceFile, ...)` stops after the unit
file and names it after the source's path; `compile_hlasm` names its source `__main__.asm`.
The module name is the path's stem, and qualifies every section variable
(`__hlasm_sect_<module>.<section>`), so private code and same-named sections in two
modules do not collide.

### Object module

The unit carries an `ObjectModule` (`interpreter/project/object_module.py`, built by
`interpreter/hlasm/assembled_module.py`), the records of IBM's object-module format:

| Record | Type | From |
|---|---|---|
| ESD SD, CM | `ControlSection`, `CommonSection` (name, length) | each CSECT, RSECT and COM in section order; private code is named "" |
| ESD LD | `EntryLabel` (name, section, offset) | each ENTRY operand, in order |
| ESD ER, WX | `ExternalReference`, `WeakReference` | EXTRN and V-constant names; WXTRN |
| ESD PR/XD | `ExternalDummySection` (name, length, alignment) | each DXD (DS-style length, strictest operand alignment) and each DSECT a Q-constant names (assembled length; doubleword, or its strictest field's alignment when stricter, so LQ gives quadword as in APAR PK79869) |
| TXT | `TextRecord` (section, offset, bytes) | each placed constant image |
| RLD | `RelocationRecord` (section, offset, length, kind, target, sign, addend) | each A, Y or V address naming a section or an external symbol (`ADDRESS`); each Q (`PR_OFFSET`), J (`CLASS_LENGTH`) and CXD (`PR_TOTAL`); a complex-relocatable A or Y constant is one signed `ADDRESS` item per term at one field, the first carrying the absolute part, a DSECT term dropped (its offset is in the absolute part) |
| END | `NamedEnd` (name, section, offset) or `DefaultEnd` (section) | END's operand, or the first CSECT |

A target is `RelocationName(name)`, or `NoRelocationTarget()` for CXD; a record whose target does not fit its kind raises `RelocationTargetMismatch` when built. Q, J and CXD fields have
no TXT. The bridge (program format 3) exports `entries`, `externals` as name, kind (`EXTRN` or
`WXTRN`) and line (0 when it has none, as for `EXTRN PART(...)`), an external address's offset,
`external_dummies` as name, length and alignment, and a `CXD` statement. A Q or J value is a
`RELOC` naming the dummy section. A complex-relocatable value is `COMPLEX`: its terms (`SECTION`
or `EXTERNAL`, name, `PLUS` or `MINUS`, one per count, sorted by name) and its absolute part. A complex-relocatable machine operand refuses the
assembly, as in HLASM, which requires those to be absolute or simply relocatable.

### Binder

`bind_image(units)` (`image_binding.py`, reached through `interpreter.frontends`) binds the
units' object modules once, at link. Start-up IR is not rebuilt from the AST.

- **Layout.** Each module is one region of its SDs at doubleword offsets in ESD order, over-allocated
  by 7 bytes so its base is doubleword aligned. Each CM name is one region at its largest length,
  shared by every module naming it. `__hlasm_sect_<module>.<section>` holds each address.
- **Names.** An RLD target resolves to a section of its own module, then to an SD or LD anywhere in
  the image, then to a COBOL program's stub, then to 0 for a WXTRN and to a stub for an EXTRN. Stubs are 8 bytes apart in one region
  (`__hlasm_stubs_low` to `__hlasm_stubs_high`), the COBOL programs' first; each unresolved EXTRN is logged once as a warning
  (`UnresolvedExternal`, kept on the job-step module) at the open-code line of its EXTRN, else of
  its first use. An address in a DSECT is its offset, as TXT with no RLD (ruling R75). Every RLD is applied after every module is
  laid out. The signed items at one field are summed and stored once, wherever they sit among the records (ORG can overlay two constants).
- **Pseudo registers.** External dummy sections merge by name across the image at their largest
  length and strictest alignment, then sit in first appearance (module order, ESD order), each
  at the next offset aligned to its alignment, from 0 (IBM leaves the order to the binder). Q
  gets the offset, J the merged length, CXD the end of the last one. The binder allocates no
  area: the program GETMAINs CXD bytes and adds Q values to the area's address, as IBM's steps
  for external dummy sections say. A J naming anything but an external dummy section raises
  `UnsupportedBinding` (red-dragon-6uyp.104). IBM allows J only under GOFF; che4z accepts it
  without, and so do we.
- **Duplicates.** An SD, LD or COBOL PROGRAM-ID name defined twice in the image raises
  `DuplicateProgramInImage` naming both units (ruling R67).
- **Job step.** Each SD and LD name gets `func___hlasm_job_<NAME>_0` in the `__hlasm_job__`
  module, registered in `programs`; each module gets `func___hlasm_end_<module>_0` for its END
  entry, which is not an external name (ruling R74). The image's `entry_func_label` is the first
  HLASM unit's END step, so `compile_hlasm` enters its main source. A step sets R1 to a one-entry VL list pointing at a halfword
  length and up to 100 bytes of PARM text, R13 to a fresh 72-byte save area, R14 to `0xFF0` and
  R15 to the entry address, then calls the module function (`__hlasm_module_<module>`) with the
  entry address and an empty set of modules below.
- **Far-branch table.** `Binder.far_branch_table()` lists (start, length, owner) for each module
  and stub; owners are `ModuleOwner`, `UnresolvedOwner` and `CobolOwner`, which holds the COBOL
  program's name, unit file and USING signature. The job-step module's `__hlasm_far_branch` is generated from it (see Control Across
  Modules).

### Control Across Modules

Each module is one IR function, `__hlasm_module_<module>(target, below)`. An activation declares
`__hlasm_return_to`, its entry R14 masked to 31 bits, and keeps `__hlasm_below`, the set of
modules with an activation under it, as bits (`__hlasm_bit_<module>`, set at start-up).
Registers stay shared machine state.

- Every branch stores its target in `__hlasm_target` and goes to `hl_dispatch`; BAL, BALR, BAS,
  BASR, BRAS, BRASL and BASSM go to `hl_link_dispatch`, which records that the branch linked.
- A target at a machine statement of the module's own sections branches to its label, even when
  it equals the return address: the same code runs either way, and a module entered at its own
  R14 must not return at once.
- Otherwise a masked target equal to `__hlasm_return_to`, or to the system's return address
  `0xFF0`, returns R15's low word. A branch to `0xFF0` from any activation therefore unwinds every
  activation up to the job step, ending the step with R15, or up to the LINK that entered it,
  or up to the COBOL CALL that entered it (ruling R82). BSM and BASSM make the same comparison before their mode test, so the mode bit of
  the return address does not matter.
- Any other target goes to `__hlasm_far_branch(target, below, me, linking)`, which finds its owner:
  - the module itself: `S0C1` (data, or a DSECT offset);
  - another module: if the branch did not link and that module is in `below`, the activation
    returns and the one below re-dispatches on the target, so `B 4(,14)` and a return that skips
    a level work; otherwise it calls `__hlasm_module_<owner>(target, below | me)` and, when that
    returns, re-dispatches on `__hlasm_target`;
  - a COBOL program's stub: the program is called with its arguments (see COBOL Linkage);
  - an unresolved stub: `CallWithMemory` on `__entry_<NAME>` with no arguments, as a static COBOL
    `CALL 'NAME'` to a missing program; the result goes to R15 and control to R14;
  - nothing: `S0C1`.

The job step's R14, `0xFF0`, is owned by nothing, so only the return test ends the outermost
activation.

### COBOL Linkage

A mixed image (`link_hlasm_units` over COBOL and HLASM unit files, `docs/linker-design.md`
§7.4) calls across the languages in IR; no builtin is added. Sources: Enterprise COBOL
Programming Guide (Table 65; "Understanding the RETURN-CODE special register"; "Testing for
OMITTED arguments"), z/OS LE Writing ILC Applications (Figure 54; the C/COBOL by-value table
and its note 3), APAR PI44924.

- **COBOL → HLASM.** Each SD and LD name gets a job-step function `__entry_<NAME>`, declared
  under that name, so a COBOL `CALL` finds it as it finds a COBOL program. It calls
  `__hlasm_from_cobol(arguments, entry)`, which writes the R1 list in a fresh doubleword-aligned
  region: BY REFERENCE and BY CONTENT an address; BY VALUE the value itself, 1, 2 and 4 bytes
  widened to one word by the item's signedness, 8 bytes in two words; OMITTED a zero word. The last word gets
  X'80000000' unless the last argument is BY VALUE. R13 gets a fresh 72-byte save area, R14
  `0xFF0`, R15 the entry. The module is entered with no modules below, and R15's low halfword
  comes back as RETURN-CODE.
- **HLASM → COBOL.** A COBOL program's stub is owned by `CobolOwner`, which holds its USING
  signature (`ModuleUnit.using`). The far branch walks the R1 list by it, at offsets known at
  link: a BY REFERENCE position takes the word's 31-bit address, OMITTED when zero, and the VL
  bit ends the walk there; a BY VALUE position copies 1, 2, 4 or 8 bytes from its slot into a
  fresh region and never ends the walk. The walk stops at the signature's length. R14–R12 are
  saved at 12(R13) and restored after the call, R13 is put back, and R15 gets RETURN-CODE
  sign-extended.
- **CANCEL** of an HLASM name does nothing: the program directory does not hold it.
- **Abends.** An HLASM abend halts the VM, so it ends the whole run unit, COBOL callers
  included.

## Diagnostics

Errors refuse the assembly. che4z's errors refuse in the bridge (`HlasmParseError`).
DC errors (ASMA064S, ASMA068S, ASMA071E, ASMA072E, ASMA073E, `UnsupportedDataType`)
are raised when the unit is lowered, while its diagnostics are collected, so
`lower_hlasm_program` refuses them too, not only linking.

Everything below error level is kept on the unit (`ModuleUnit.diagnostics`, from
`HlasmFrontend.diagnostics`). It is logged through the `interpreter.hlasm` logger
each time `compile_hlasm` or `lower_hlasm_program` uses the unit, whether built or
reused. The records come from the files in hand: `compile_hlasm` reads them from the
linked file, `lower_hlasm_program` from the unit it built or read. They never stop
the run. Two sources:

- che4z's diagnostics: its warnings, and MNOTEs below severity 8. che4z classifies
  MNOTE 4-7 as warnings, 2-3 as info and 0-1 as hints. Warnings log at `WARNING`;
  info and hints at `INFO`. Our bridge exports each diagnostic's MNOTE form as its
  own field (`Diagnostic.mnote`): `MnoteLevel` with the severity, `MnoteComment`
  for `MNOTE *,'text'` and `MNOTE 'text'` (che4z reads both as level 0; our fork
  keeps the form), or `NoMnote`. The unit keeps it as the record's `kind`:
  `SeverityMnote`, `CommentMnote`, or `CodedDiagnostic` with che4z's code.
  che4z's codes are its own, not IBM's `ASMA` ids.
- `DcWarning`s from E, D and L constants with a type extension, at `WARNING`, at the
  DC statement's line: `EB'1E39' overflow`. A macro-generated DC takes the call's
  line and names the macro (`EB'1E39' overflow in macro GEN`); a literal takes its
  first use. A duplicated operand warns once per value. Every DC is checked, DSECTs
  and duplication factor 0 included: HLASM checks their nominal values though it
  emits no object code for them (ruling R63).

Each record (`UnitDiagnostic`) holds the severity, a typed kind, the place and the
macro call stack, innermost call first. The kind carries the facts:
`CodedDiagnostic(code, text)`, `SeverityMnote(level, text)`, `CommentMnote(text)`,
or `ConstantDiagnostic(constant, warning, source)` with a `DcWarningKind` and
`InMacro(name)` or `InOpenCode()`. Only the log line renders them, as the listing
shows an MNOTE: `CAREFUL:3: MNOTE 4,MIND THE GAP (called from __main__.asm:2)`,
`MNOTE *,ASIDE` for a comment, `A300 <text>` for a coded diagnostic, and the
constant and its warning (`EB'1E39' overflow`, `EB'1E-50' underflow in macro
CAREFUL`) for a DC warning. A SYSLIB member's
`file://` URI is shown as the member name; open code keeps its source name.

## Assembly Inputs

`HlasmCompileOptions.names` maps an `AssemblyInput` to its value, and the bridge gets
each one as an option (`--sysparm`, `--sysjob`, `--sysstep`, `--sysin-dsn`,
`--sysin-member`). An unsupplied `&SYSPARM` is the null string, as in HLASM. Any other
name that was not given is undefined, and reading it refuses the assembly with
`E010 Unknown variable: <name>` at its line (`HlasmParseError`). A SYSPARM over 255
characters, HLASM's limit, or a clock reading without a UTC offset raises
`UnusableAssemblyInput` before the bridge runs. `&SYSJOB`, `&SYSSTEP` and
`&SYSPARM` are global; `&SYSIN_DSN` and `&SYSIN_MEMBER` exist only inside macros, as
che4z defines them. No CLI flag supplies them yet.

The clock is read once per assembly, when the bridge runs, and passed as an ISO
instant with its UTC offset (`--clock`); the bridge refuses a field out of range. `&SYSDATE`, `&SYSDATC`, `&SYSTIME` and
`AREAD CLOCKB`/`CLOCKD` use its local time. `&SYSCLOCK` uses its UTC time, so every
macro call sees the same `&SYSCLOCK`; HLASM takes a new reading per call.

`&SYSSEQF` is columns 73-80 of the open-code statement that called the macro,
directly or through other macros, padded to 8 with blanks. che4z ignores ICTL and
ISEQ for this, as it does for line layout.

che4z has no other data-set variables (`&SYSIN_VOLUME`, `&SYSLIB_*`, `&SYSPRINT_*`,
`&SYSPUNCH_*`, `&SYSTERM_*`, `&SYSADATA_*`, `&SYSLIN_*`); they stay `E010`.

The entry is the symbol `END` names, or the first CSECT at offset 0 when `END`
names none. The module function's label is `func_<entry>_0`. It returns GR15's low word
when control branches to its return address.

## Supervisor Calls and Our Maclib

`get_hlasm_parser` puts `hlasm-bridge/maclib/` ahead of any caller's SYSLIB.
`run()` and the tests assemble through it; `run(copybook_dirs=...)` supplies the
caller's SYSLIB directories, searched after ours. The macros follow the z/OS operand
conventions but expand only to lowered opcodes:

| Macro | Expansion |
|---|---|
| `WTO 'text'` | `BRAS 1` around an inline list (AL2 length including the 4-byte header, AL2 MCS flags, the text), then `SVC 35` |
| `ABEND code` | `LA 1,code` (user code, bits 20-31), then `SVC 13` |
| `ABEND code,,,SYSTEM` | `LA 1,code`, twelve `LA 1,0(1,1)` doublings into bits 8-19, then `SVC 13`. `DUMP` and `STEP` are accepted and ignored. |
| `SAVE (r1,r2)[,T][,id]` | With an `id` (`*` is the macro's label, else the CSECT name; up to 70 characters), `J` around `AL1(length),CL'id'` first, so the count byte is at entry+4 and the text at entry+5. Then `STM r1,r2` at byte `(r1*4+20) mod 64` of the R13 save area; with `T` and `r1` not 14, also `STM 14,15,12(13)`. |
| `RETURN (r1,r2)[,T][,RC=n\|(15)]` | `LM` over the same slots, then `MVI 12(13),X'FF'` for `T`, `LA 15,n` for `RC=n`, then `BR 14`. `RC=(15)` (or `(R15)`) never reloads R15: `(14,12)` is `L 14,12(13)` and `LM 0,12,20(13)`, `(14,15)` is `L 14,12(13)`. R13 is restored only if it is in the range. |
| `YREGS` | `R0` to `R15` as `EQU`s |
| `GETMAIN R,LV=n\|(r)[,SP=n\|(r)]` | R0 = length, `SP` in bits 32-39 (`NILH`/`OILH`, or `LR`, `SLL`, `OR` through R15 for `SP=(r)`). `LV=(0)` keeps R0 as given, subpool included. `BRAS 1,*+4` makes R1 negative; `SVC 10` |
| `FREEMAIN R,LV=,A=addr\|(r)[,SP=]` | R1 = `L 1,addr` or `LR 1,r`, R0 as for GETMAIN; `SVC 10` |
| `GETMAIN RU\|RC`, `FREEMAIN RU\|RC` | IBM's layout: R0 = length, R15 = subpool × 256 + flags (X'01' release, X'02' unconditional, X'04' page); `SVC 120`. `SP=(r)` takes the register's low byte (`LLCR`, `SLL`, `OILL`) |
| `STORAGE OBTAIN\|RELEASE,LENGTH=,ADDR=[,SP=][,COND=][,BNDRY=][,LOC=]` | As the SVC 120 forms. OBTAIN stores R1 with `ST 1,addr`, or `LR r,1` for `ADDR=(r)`; RELEASE loads R1 from `ADDR` as FREEMAIN does from `A` |
| `TIME [DEC\|BIN][,LINKAGE=SVC]` | `LA 1,2` (DEC) or `LA 1,1` (BIN), IBM's codes, then `SVC 11` |
| `CALL ep\|(15)\|(r)[,(p,...)][,VL]` | `BRAS 1` around `DC AL4(p),...` (unaligned, so the list starts where R1 points; VL adds X'80000000' to the last word), `L 15,=V(ep)` or `LR 15,r`, `BALR 14,15` |
| `CALL ,(p,...)[,VL],MF=L` | The list alone: `DC A(p),...` under the call's label |
| `CALL ep,(p,...)[,VL],MF=(E,list\|(r))` | `LA 1,list` or `LR 1,r`, then `LA 14,p` and `ST 14,4i(,1)` per parameter, `OI` on the last for VL, then as above |
| `LINK EP=\|EPLOC=[,PARAM=(p,...)][,VL=1]` | PARAM as CALL's inline list; `BRAS 15` over IBM's control list `AL4(name,0)` (`EPLOC=(r)` stores r into it, so the standard form is not reentrant, as IBM's is not); `SVC 6` |
| `LOAD EP=\|EPLOC=[,ERRET=addr]` | R0 → the name (`BRAS 0` over `CL8'ep'`, `LA 0,addr` or `LR 0,r`); `LA 1,0`, with ERRET `OILH 1,X'8000'`; `SVC 8`; with ERRET `LTR 15,15` and `BNZ addr` |
| `DELETE EP=\|EPLOC=` | R0 as LOAD; `SVC 9` |
| `DCB DSORG=PS,MACRF=,RECFM=,LRECL=,BLKSIZE=,DDNAME=,EODAD=,SYNAD=` | 96 bytes at IBM's offsets: DSORG 26 (PS X'40'), EODAD 33 (3 bytes, 1 when omitted, as IBM), RECFM 36 (F X'80', FB X'90', V X'40', VB X'50'), DDNAME 40, OFLGS 48, MACRF 50 (GM X'5000', GL X'4800', PM X'0050', PL X'0048', summed over a list), SYNAD 57, BLKSIZE 62, LRECL 82 |
| `DCBD` | DSECT `IHADCB`: `DCBDSORG`, `DCBEODAD`/`DCBEODA`, `DCBRECFM`, `DCBEXLSA`, `DCBDDNAM`, `DCBOFLGS`, `DCBMACR` (`DCBMACR1`, `DCBMACR2`), `DCBSYNAD`/`DCBSYNA`, `DCBBLKSI`, `DCBLRECL`; `DCBDSGPS`, `DCBRECF`, `DCBRECV`, `DCBRECBR`, `DCBOFOPN` (X'10'). Operands are ignored |
| `OPEN (dcb,(opt),...)` | `CNOP 0,4`, `BRAS 1` over the list `AL1(opt),AL3(dcb)`, X'80' on the last option; INPUT 0, OUTPUT 15, EXTEND 14; `SVC 19` |
| `CLOSE (dcb,,...)` | The same list with option 0; `SVC 20` |
| `GET dcb[,area]`, `PUT dcb[,area]` | R1 → the DCB, R0 → the area (`LA`, or `LR` for `(r)`); `LARL 14` past the SVC and `OILH 14,X'8000'`, as a BALR in AMODE 31 leaves it; `SVC 200` / `SVC 201` |

`LOC` is accepted and ignored: storage is never constrained below 16 MB. `BNDRY` is `DBLWD`
or `PAGE`, and `PAGE` only on the SVC 120 forms. Missing `LV`, `LENGTH`, `A` or `ADDR`,
another type, `COND` other than `YES` or `NO`, `SP=(r)` outside 2-12, `SP` with
`R,LV=(0)`, `LV=(1)` or `LENGTH=(1)` on a release, TIME types other than `DEC` and `BIN`,
and `LINKAGE` other than `SVC` are `MNOTE 8`. So are a CALL third operand other than `VL`, `MF`
other than `L` or `(E,list)`, `MF=L` without a list, a missing entry or a bad register; LINK `VL`
other than 1; and on LINK, LOAD and DELETE, no `EP` or `EPLOC`, both, an `EP` over 8 characters,
or an `EPLOC` register outside 2-12 (IBM's range). On DCB, `DSORG` other than `PS`, `MACRF` other than
`GM`, `GL`, `PM`, `PL`, `RECFM` other than `F`, `FB`, `V`, `VB`, and a self-defining `EODAD` or `SYNAD`
at or above 2^24 (they are 3-byte fields) are `MNOTE 8`, and so is an OPEN option other than
`INPUT`, `OUTPUT` or `EXTEND`.

Registers may be numbers or `Rn`. A bad register, a third range entry, a second operand other than `T`, or
an `RC` register other than 15 is an `MNOTE 8`, which refuses the assembly. Save areas
are the 72-byte format-0 area. The differential tests run against z390's `mac/` library, whose `SAVE` and `RETURN` ignore `T` and the
identifier, so they expect its flag and R14/R15 slots to differ; the identifier layout rests on the VM tests.

SVCs are lowered in IR over existing builtins. The services use the table membership
builtin, the string and list builtins, the TOD clock builtin, the COBOL file provider's
primitives, `__hlasm_dd` and `__hlasm_declare_file`.

- **SVC 35** reads the text length from the list at R1, copies the text a byte at a
  time, decodes it from EBCDIC and writes it as one line with `println`.
- **SVC 13** records `S` and three hex digits when bits 8-19 of R1 are non-zero,
  otherwise `U` and four decimal digits, in `__hlasm_abend`, then halts.
- **SVC 10** obtains when R1 is negative, else releases the area at R1. The length is R0's
  low 24 bits, the subpool R0's high byte. **SVC 120** takes the length from R0 and the
  subpool and flags from R15, and sets R15 to 0.
- **Obtaining** rounds the length up to 8, allocates one region of that length plus the
  alignment less one, and returns the aligned address inside it in R1: doubleword, or page
  for `BNDRY=PAGE`. Storage is always obtained, so `RC` and `COND=YES` return 0.
- **The allocation table** `__hlasm_allocations` is a `NEW_OBJECT` created at start-up,
  indexed by address. Each entry is an object with fields `length` (rounded) and
  `subpool`.
- **Releasing** needs an entry at the address with the same rounded length and subpool,
  else it abends `SA0A` (SVC 10) or `SA78` (SVC 120). The entry's length becomes -1, so a
  second release abends. Freed storage is not reused, and releasing part of an area abends.
- **SVC 11** reads `__hlasm_tod_clock`. The format bits of R1's low byte select the format,
  as on z/OS; the GMT and ERRET flag bits are ignored. 1 is BIN (R0 = binary hundredths
  since midnight), any other value DEC (R0 = packed `HHMMSSth`); TU, MIC and STCK (0, 3, 4)
  are not lowered. R1 is then the date as packed
  `0CYYDDDF` (C is 0 for 19xx, 1 for 20xx). R15 is 0. No zone offset is applied, so local
  time is the TOD clock's UTC; leap seconds are ignored.
- The SVC 6, 8 and 9 inputs are IBM's: SVC 6 takes R15 → `A(name),A(DCB)` and R1 the parameter
  list; SVC 8 R0 → the name and R1 the DCB address, its high bit asking for a return on error;
  SVC 9 R0 → the name. The DCB is ignored.
- **SVC 6** (LINK) reads the 8-byte EBCDIC name and looks its image up in `__hlasm_names`, a
  start-up object of the image's SD and LD names, each an entry of `address`, `length` (the
  owning module's region in doublewords) and `loads`. Found, it sets R14 to `0xFF0` and R15 to
  the entry and calls `__hlasm_far_branch` as a linking branch with nothing below (Control
  Across Modules). The registers come back as the program left them (IBM's LINK register
  information). Missing, it issues `CallWithMemory` on `__entry_<NAME>`, the name decoded,
  trimmed and uppercased at run time (z/OS load-module names are uppercase), exactly as a COBOL `CALL identifier` to a missing program: that raises
  `UnresolvedProgramError` whether or not unresolved targets are permitted (ruling R80).
- **SVC 8** (LOAD) sets R0 to the entry with bit 32 on, R1 to the length in doublewords (APF
  byte 0) and R15 to 0, and counts the load. A missing name with R1's high bit on returns with R1
  `X'00806000'` and R15 4 (806, reason 04, "not found"); without it, it abends `S806`.
- **SVC 9** (DELETE) takes one counted load back and sets R15 to 0; a name not loaded by the run
  unit, or not in the image, gets R15 4. Nothing is freed.
- **SVC 19** (OPEN) walks the list at R1 to the entry with X'80'. For each DCB: the DDNAME at
  offset 40, cut at the first blank; `__hlasm_dd` for it; an unsupplied DD fails the entry.
  Each zero RECFM, LRECL and BLKSIZE takes the DD's and is written back. The mode is the
  option's low four bits (0 INPUT, 15 OUTPUT, 14 EXTEND; any other fails the entry), checked
  before any DD value is written, so a failed entry leaves the DCB as it was. An LRECL still 0
  after the merge abends `S013` (ruling R85). OPEN
  declares the file (`__hlasm_declare_file`, V with LRECL less the RDW) and calls
  `__cobol_open_file`; a result other than OK fails the entry. An opened DCB gets DCBOFOPN and,
  with MACRF GL or PL, an LRECL buffer obtained as GETMAIN obtains, kept in
  `__hlasm_dcb_buffers` by DCB address with a pending-PUT flag. R15 is 0, or 8 if any entry
  failed. A failed DCB keeps DCBOFOPN off.
- **SVC 20** (CLOSE) writes a pending locate-mode record, calls `__cobol_close_file` and turns
  DCBOFOPN off for each open DCB in the list. R15 is 0.
- **SVC 200** (GET) reads with `__cobol_read_record`. At end of data it branches to EODAD (R14
  is the GET macro's), or abends `S337` when EODAD is 0 or 1 (the DCB macro's default). A RECFM V
  record gets its RDW in front. Move mode copies it to R0's area a byte at a time; locate mode
  copies it to the DCB's buffer and returns that address in R1.
- **SVC 201** (PUT) writes LRECL bytes from the area for RECFM F, or the RDW's length less 4
  bytes after the RDW for V; a V record whose RDW length exceeds DCBLRECL abends `S002` before the
  provider is called (ruling R86). Locate mode writes the buffer's pending record, if any, and
  returns the buffer in R1; CLOSE writes the last one, as IBM's does.
- GET or PUT on a DCB without DCBOFOPN abends `S0C1`: IBM's macros branch through the DCB's
  routine field, which an unopened DCB does not hold, and an unowned branch here abends `S0C1`.
- Driver outcomes are compared by `AccessCondition` position, from `interpreter.record_io`.
- **Any other SVC number** logs the number and abends `S0C1`. This is a project
  choice, not z/OS behaviour.

WTO costs about 15 VM steps per character, so `run()` needs `max_steps` well
above its default of 100.

Every IR instruction a statement lowers to carries that statement's line as its
source location. A macro-generated statement carries the line of the macro call
in the open-code source. Columns are 0: the bridge reports lines only.

## Macro Language

che4z runs the macro language; the bridge exports only the ordinary statements it
generates. `tests/integration/hlasm/macro_language_programs.py` holds one program per
feature, run on the VM and, under `tests/z390/`, in z390. Tests carry `HlasmFeature`
tags (`interpreter/hlasm/features.py`). Covered:

- Nested and inline macro definitions, `&SYSNDX` labels, AIF/AGO loops under ACTR,
  ANOP. A loop past its ACTR count refuses the assembly (che4z E056; HLASM ends the
  expansion with an error).
- GBLx and LCLx scope; SETA, SETB and SETC expressions with bitwise operators,
  substrings, duplication and UPPER; created (`&(name)`) and subscripted SET symbols.
- Positional parameters, `&K=` parameters with defaults, sublists, `&SYSLIST`, N'
  and K'.
- Opcode substitution, OPSYN rename and delete, AREAD, AINSERT FRONT and BACK, COPY
  from SYSLIB (`.mac` for us, `.CPY` and `.MAC` for z390).
- DSECTs with USING, labeled and dependent USING; S-constant literals whose pools
  are moved by LOCTR and ORG.
- T', L', S', I', D' and O'; T' and D' of literals.
- `&SYSECT` and `&SYSLOC` across LOCTRs and CSECTs; `&SYSSEQF` and `&SYSSTMT` from
  open code, a COPY member, after lookahead and in a SYSLIB macro; `&SYSPARM` empty
  and given; `&SYSDATC`, `&SYSTIME` and `&SYSDATE` from the injected clock (VM only:
  z390 reads its own clock).
- An MNOTE from a macro reaches the log (VM only: z390 writes MNOTEs to its listing).

Our che4z fork follows the Language Reference in three places:

- T' of a literal named by a macro operand is the constant's type only if a machine
  instruction already used that literal; otherwise U. A literal written in the macro
  body keeps its constant's type.
- `&SYSSTMT` is the next statement number, inside an expansion as in open code.
  Statements of a SYSLIB macro definition are not numbered. Which statements an
  expansion numbers is not in the manual; we follow che4z, which numbers each one.
- A literal's pool is matched by literal-pool generation, so its S-constants use the
  USING at its own LTORG wherever LOCTR puts it.

Where z390 disagrees, a z390 test pins z390's value (red-dragon-6uyp.74): I' is 0,
S' is 0 for a symbol defined later, T' of a literal is U and D' is 0, `&SYSSEQF` is
empty, `&SYSSTMT` counts open-code lines only, and an attribute of a literal in a
macro body does not assemble.

## Differential Tests Against z390

`tests/z390/` runs each program in RedDragon and in z390 and compares the return
code, the abend code and the WTO lines. Under z390 the program assembles against
z390's own macro library. The tests carry the `z390` marker, which the default run
excludes. Build z390 (`javac` the sources into `z390.jar`, as its `bash/bldjar`
does), then:

```bash
Z390_HOME=/path/to/z390 uv run pytest -m z390 tests/z390 -n0
```

`Z390_HOME` unset fails the tests rather than skipping them. `Z390Runner` runs
`bash/asmlg` and reads the program's `.LOG`. The return code comes from the
`EZ390 ENDED RC=` line, or is 0 after an abend. The abend code comes from
`program aborting due to abend`. The WTO lines are the run's lines minus z390's
`EZ390` messages and register dumps. Extra asmlg options go through `run`, for
example `SYSPARM(ALPHA)`.

Registers and the CC are compared through `HlasmMachine`: `run_hlasm_machine` reads
all 16 GPRs (64-bit) and `__hlasm_cc`; `Z390Runner.run_machine` reads them from the
dump z390 prints on an abend, the CC from the `ABEND PSW` (short, or 16 digits in AMODE 64). So a register test ends
in `ABEND n`, which both maclibs expand to `LA 1,n` and `SVC 13`. Compare only the
registers the test declares (`restricted_to`): z390 starts the high words at
`F4F4F4F4` and R0, R1, R13, R14 and R15 at its own values. A declared register that a
32-bit instruction writes needs its high word set first, by `LG` or `LMG`.
A run that leaves no `.LOG` raises `Z390AssemblyFailed` with asmlg's exit code
and the `.ERR` text. The machine starts with program mask `0110` (decimal overflow
and HFP exponent underflow on), as z390's initial PSW `07850600` does.

## Opcode Units

Storage is the VM's flat byte memory: `HlasmEmitter.load_storage` and
`store_storage` read and write a compile-time width at an address as an integer;
`load_bytes` and `write_bytes` move the raw bytes at a register offset. A 32-bit
result writes only the GPR's low word.

**Load and store (red-dragon-6uyp.23).** L, LY, LG, LGF, LH, LHY, LGH, LB, LGB,
LLC, LLGC, LLH, LLGH, LLGF, LLGT, LZRF, LZRG, LLZRGF, LRV, LRVG, LRVH, IC, ICY,
LGG, LLGFSG; the register forms LR, LGR, LBR, LGBR, LHR, LGHR, LGFR, LLCR, LLGCR,
LLHR, LLGHR, LLGFR, LLGTR, LRVR, LRVGR; relative-long LRL, LGRL, LGFRL, LLGFRL,
LHRL, LGHRL, LLHRL, LLGHRL, STRL, STGRL, STHRL; ST, STY, STG, STH, STHY, STC,
STCY, STRV, STRVG, STRVH; LM, LMY, LMG, STM, STMY, STMG, LMD (R1 to R3 wraps from
R15 to R0); ICM, ICMY (CC from the inserted bits), STCM, STCMY.

- Guarded storage is never enabled, so LGG and LLGFSG never raise a guarded-storage
  event. In AMODE 31 they keep bits 33-63 of the loaded value; LLGFSG's shift is 0.
- Word and doubleword relative-long operands, LGG and LLGFSG check alignment and
  abend `S0C6`. z390 does not check relative-long alignment; the z390 test pins
  that difference.
- z390 refuses a relative-long operand in another CSECT, so the z390 tests keep
  relative operands in the same section; the VM tests cross sections.

**Load address and immediates (red-dragon-6uyp.24).** LA, LAY, LAE, LAEY, LARL;
LXAB, LXAH, LXAF, LXAG, LXAQ, LLXAB, LLXAH, LLXAF, LLXAG, LLXAQ; LHI, LGHI, LGFI;
LLIHF, LLIHH, LLIHL, LLILF (LLGFI), LLILH, LLILL (LLGHI); IIHF, IIHH, IIHL, IILF
(LFI), IILH, IILL. None changes the CC.

- Addresses go into bits 33-63 with bit 32 zero; the high word is kept.
- LXA* and LLXA*: (low word of X2 + DX2) shifted left 0-4, plus B2. In AMODE 31
  only bits 33-63 are kept, and they depend only on the low 31 bits of each term,
  so the signed and logical forms agree. che4z types their R1 as a mask operand.
  z390 does not execute them (`S0C1`); their tests use values from the Principles
  of Operation.
- The bridge hands an immediate signed or unsigned (`LLILF X'FFFFFFFF'` arrives as
  -1), so each lowering takes its field-width bit image first.
- z390 raises `S0C5` for LAE and LAEY at an address beyond its storage; the
  Principles of Operation make no storage reference. The z390 test pins that difference.

**Signed add and subtract (red-dragon-6uyp.25).** A, AY, AR, ARK, AH, AHY, AHI,
AFI, AHIK, ASI, AG, AGR, AGRK, AGF, AGFR, AGH, AGHI, AGFI, AGHIK, AGSI; S, SY, SR,
SRK, SH, SHY, SG, SGR, SGRK, SGF, SGFR, SGH. CC 0 zero, 1 negative, 2 positive,
3 overflow.

- Overflow keeps the wrapped result and sets CC 3. When program-mask bit `1000`
  (fixed-point overflow) is on, the run then abends `S0C8`. The initial mask has it
  off.
- AGF, AGFR, SGF, SGFR sign-extend a 32-bit second operand; AH, AHY, AGH, SH, SHY,
  SGH a halfword; AHI, AGHI, AHIK, AGHIK a 16-bit immediate; ASI, AGSI an 8-bit one.
- ASI and AGSI read, add and write back the storage operand.
- SR moved here from the seed module and gained the `S0C8` check.

**Logical add and subtract (red-dragon-6uyp.26).** AL, ALY, ALR, ALRK, ALFI, ALHSIK,
ALSI, ALG, ALGR, ALGRK, ALGF, ALGFR, ALGFI, ALGHSIK, ALGSI, ALC, ALCR, ALCG, ALCGR; SL,
SLY, SLR, SLRK, SLFI, SLG, SLGR, SLGRK, SLGF, SLGFR, SLGFI, SLB, SLBR, SLBG, SLBGR.
CC = 2 × carry + (result ≠ 0). No overflow interruption.

- Subtraction is first + ones' complement of second + carry-in: 1 for SL forms, CC bit 2
  (CC 2 or 3) for SLB forms. A borrow is no carry, so SL sets CC 1, 2 or 3; SLB can set
  CC 0. ALC forms add CC bit 2.
- ALGF, ALGFR, ALGFI, SLGF, SLGFR, SLGFI zero-extend a 32-bit second operand.
- ALHSIK, ALGHSIK (16-bit) and ALSI, ALGSI (8-bit) sign-extend the immediate and add it
  unsigned. For a negative immediate that is SUBTRACT LOGICAL of its magnitude, the CC the
  Principles of Operation prescribe.
- z390 sets a different CC for ALGRK and SLGRK (its CC helper reads stale operands) and
  for the signed-immediate forms (it reports a borrow as a carry). The z390 test pins
  each difference.

**Compare (red-dragon-6uyp.28).** Signed C, CY, CR, CFI, CRL, CH, CHY, CHI, CHRL, CHSI,
CHHSI, CG, CGR, CGRL, CGF, CGFR, CGFI, CGFRL, CGH, CGHI, CGHRL, CGHSI; logical CL, CLY,
CLR, CLFI, CLRL, CLHRL, CLFHSI, CLHHSI, CLI, CLIY, CLG, CLGR, CLGRL, CLGF, CLGFR, CLGFI,
CLGFRL, CLGHRL, CLGHSI, CLM, CLMY. CC 0 equal, 1 first operand low, 2 high; nothing is
stored.

- The CC is the sign of first − second, each taken signed or unsigned at the compare width.
- Signed forms sign-extend a shorter second operand; logical forms zero-extend it. CHHSI and
  CLHHSI compare 16 bits, CLI and CLIY 8.
- CLM and CLMY compare the low-word bytes the mask selects with that many storage bytes.
  Mask 0 sets CC 0 and reads no storage.
- Word and doubleword relative-long operands check alignment and abend `S0C6`; z390 does
  not, and the z390 test pins that difference.

**Compare and branch, compare and trap, load and trap (red-dragon-6uyp.29).** CRB, CGRB,
CLRB, CLGRB, CIB, CGIB, CLIB, CLGIB (branch to D4(B4)); CRJ, CGRJ, CLRJ, CLGRJ, CIJ, CGIJ,
CLIJ, CLGIJ (relative); CRT, CGRT, CLRT, CLGRT, CIT, CGIT, CLFIT, CLGIT, CLT, CLGT (trap);
LAT, LGAT, LLGFAT, LLGTAT. None changes the CC. The bridge resolves the extended mnemonics
(CRJE, CLGTNL, ...) to the base mnemonic with M3: E 8, L 4, H 2, NE 6, NL 10, NH 12.

- The comparison is the compare unit's, at 32 or 64 bits, signed or logical; its result
  (equal 8, low 4, high 2) is tested against M3 and never stored. CIB, CGIB, CIJ, CGIJ take
  a signed 8-bit I2; CLIB, CLGIB, CLIJ, CLGIJ an unsigned one; CIT, CGIT a signed 16-bit
  I2; CLFIT, CLGIT an unsigned one. CLT and CLGT compare with storage at D2(B2).
- M3 bit 3 is ignored. Bits 0-2 all zero lower to nothing; all one branch or trap without
  comparing (CLT and CLGT then read no storage, which the Principles of Operation allow).
- Branch targets go through `hl_dispatch`.
- A trap is the compare-and-trap data exception: the operation completes, then the run
  abends `S0C7` with DXC X'FF' in FPC byte 2. Load-and-trap does the same.
- LAT loads the low word (high word kept), LGAT the doubleword, LLGFAT a word zero-extended,
  LLGTAT bits 1-31 zero-extended. The register is written, then a zero value traps.
- z390 abends `S0FF` for a load-and-trap trap (it raises the DXC as the interruption code),
  and does not execute CLT or CLGT (`S0C1`). The z390 test pins both; the CLT and CLGT
  expectations come from the Principles of Operation.

**Boolean (red-dragon-6uyp.30).** N, NY, NR, NRK, NG, NGR, NGRK, NI, NIY, NC, NIHF, NIHH,
NIHL, NILF, NILH, NILL; O, OY, OR, ORK, OG, OGR, OGRK, OI, OIY, OC, OIHF, OIHH, OIHL, OILF,
OILH, OILL; X, XY, XR, XRK, XG, XGR, XGRK, XI, XIY, XC, XIHF, XILF; NCRK, NCGRK (AND with
complement), OCRK, OCGRK (OR with complement), NNRK, NNGRK (NAND), NORK (NOTR), NOGRK
(NOTGR) (NOR), NXRK, NXGRK (NOT exclusive OR). CC 0 result zero, 1 nonzero.

- The register-immediate forms combine I2 with one field of R1 (NIHH bits 0-15 ... NILF
  32-63) and replace only that field. The CC reflects that field alone.
- NC, OC and XC run one IR loop over the L bytes, left to right, storing each result byte
  before the next is fetched, so overlapping operands follow the Principles of Operation
  (`XC A,A` clears; `OC A+1(n),A` propagates the first byte). The loop is not unrolled;
  each byte is fetched, combined, stored and OR-ed into `__hlasm_ss_any`, and the CC is set
  once after the loop. The bridge passes L as written; an explicit 0 runs one byte, as the
  assembled length code 0 does.
- z390 leaves the CC unchanged for NIHF, NILF, OIHF, OILF, XIHF and XILF, sets it from the
  whole 32-bit word for the halfword forms, sign-extends the byte in XI (a zero result with
  both bytes over `X'7F'` sets CC 1), and runs OC in 8-, 4-, 2- and 1-byte pieces, so overlap
  differs. The z390 test pins each difference.

**Shift and rotate (red-dragon-6uyp.31).** SLL, SLLK, SLLG, SRL, SRLK, SRLG, RLL, RLLG
(CC unchanged); SRA, SRAK, SRAG, SLA, SLAK, SLAG (CC 0 zero, 1 negative, 2 positive, 3
overflow); SLDL, SRDL, SLDA, SRDA; RISBG, RISBGN, RISBHG, RISBLG, RNSBG, ROSBG, RXSBG.
The amount is the low six bits of the D2(B2) address; no storage is referenced.

- The left signed shifts keep the sign and shift the numeric bits. CC 3 when a bit unlike
  the sign leaves the numeric part (the exact product by 2^n does not fit); program-mask
  bit `1000` then abends `S0C8`.
- The double shifts treat the low words of R1 and R1+1 as one 64-bit operand. An odd R1
  abends `S0C6`; che4z refuses one at assembly, so only a built statement reaches it.
- The RISBG family rotates the 64-bit R2 left by I5 (absent is 0) and works on the bits
  from I3 to I4, wrapping. RISBG and RISBGN replace them in R1, and Z (I4 bit 0) zeroes
  the rest; RISBG sets the CC from the signed 64-bit result. RISBHG and RISBLG take the
  positions within the high or low word, wrap within it, and Z zeroes only that word; CC
  unchanged. RNSBG, ROSBG and RXSBG combine those bits with R1, set CC 0 or 1 from them,
  and replace them unless T (I3 bit 0) is on. The bridge resolves the extended mnemonics
  (RISBGZ, RNSBGT, LHHR, SLLHH, NHHR, ...) into these with the PoO immediates.
- z390's 32-bit shifts (SLL, SRL, SLLK, SRLK, SRA) take the amount mod 32 (Java int
  shifts), so `SRL 2,33` shifts by 1; it does not execute RISBGN (`S0C1`); and it fails
  to assemble SLLHH, SLLHL, SRLHH, SRLHL, SLLLH and SRLLH. The z390 test pins each difference.

**Load and test, complement, positive, negative (red-dragon-6uyp.40).** LT, LTR, LTG, LTGR,
LTGF, LTGFR load and set CC 0 zero, 1 negative, 2 positive; LTGF and LTGFR sign-extend a
word. LCR, LCGR (two's complement) and LPR, LPGR (absolute value) overflow only on the
maximum negative number: it stays, CC 3, and program-mask bit `1000` abends `S0C8`.
LCGFR and LPGFR sign-extend the low word of R2 first, so they never overflow. LNR, LNGR,
LNGFR never overflow. 32-bit forms write only the low word of R1.

- z390's LTGR sets the CC but does not write R1; the z390 test pins it (bead
  red-dragon-6uyp.74).

**Test under mask (red-dragon-6uyp.38).** TM and TMY test one storage byte against I2; TMHH,
TMHL, TMLH, TMLL test bits 0-15, 16-31, 32-47, 48-63 of R1 against a halfword I2. CC 0 when
the selected bits are all zero or the mask is zero, 3 when all are one. Mixed gives CC 1,
except in the register forms where it gives 2 when the leftmost selected bit is one. TMH is
TMLH and TML is TMLL; the bridge delivers them under their own names. Nothing is stored.

**Multiply and divide (red-dragon-6uyp.27).** MS, MSY, MSR, MSFI, MH, MHY, MHI, MSG, MSGR,
MSGF, MSGFR, MSGFI, MGH, MGHI keep the low 32 or 64 bits of the signed product; CC
unchanged, no overflow. MSC, MSRKC, MSGC, MSGRKC do the same and set CC 0-3, 3 when the
product does not fit; program-mask bit `1000` then abends `S0C8`. MSRKC, MSGRKC and MGRK
multiply R3 by R2.

- M, MFY, MR (signed) and ML, MLR (logical) multiply the low word of R1+1 into a 64-bit
  product in the low words of R1 and R1+1. MG, MGRK (signed) and MLG, MLGR (logical) put a
  128-bit product in R1 and R1+1. CC unchanged.
- D, DR, DL, DLR divide the low words of R1 and R1+1 by a word; DLG, DLGR divide R1 and
  R1+1 as 128 bits by a doubleword; DSG, DSGR, DSGF, DSGFR divide R1+1 by a doubleword or a
  signed word. The remainder goes to R1, the quotient to R1+1. The quotient truncates
  toward zero and the remainder takes the dividend's sign, built from magnitudes because
  the VM's `//` floors. CC unchanged.
- A zero divisor or a quotient out of range abends `S0C9` before any register is written;
  the program mask does not apply.
- Every pair form abends `S0C6` on an odd R1.
- z390 checks only the zero divisor in D, DR, DL, DLR, DSG, DSGR, DSGF and DSGFR: an
  oversized quotient is truncated and stored. In DLG and DLGR it raises fixed-point
  overflow (`S0C8`, masked by the initial program mask, so the run goes on) instead of
  `S0C9`. The z390 test pins one case per mnemonic, DLG and DLGR for the 128-bit pair.

**Branch on condition (red-dragon-6uyp.32).** BC, BCR, BIC, BRC, BRCL, BPP, BPRP. The
bridge hands every extended mnemonic (B, BE, BNER, BIL, J, JLNOP, BRUL, ...) over as its
base mnemonic with the mask filled in. The branch is taken when mask bit `8 >> CC` is one;
the CC is unchanged.

- Mask 0 lowers to nothing; mask 15 branches without testing the CC.
- BC branches to the D2(X2,B2) address, BCR to R2, BRC and BRCL to the relative target.
  BCR with R2 = 0 does not branch, so BCR 15,0 and BCR 14,0 (serialization) are no-ops.
- BIC branches to the doubleword stored at D2(X2,B2), read only when the branch is taken.
  AMODE 31 keeps its bits 33-63.
- BPP and BPRP are hints with no architected effect and lower to nothing.
- Every target, relative ones included, goes through `hl_dispatch`; a target that is not a
  machine statement of any module abends `S0C1`. Branching straight to a static relative target's label
  is deferred as a performance item (red-dragon-6uyp.80).
- z390 branches BIC to the operand address instead of the doubleword stored there, and
  abends `S0C1` on BPP and BPRP. A branch into data runs the data bytes in z390 (J, BC
  and BRCL to FILL end `S0C2`); here it abends `S0C1`. The z390 test pins all three.

**Branch and link (red-dragon-6uyp.33).** BAL, BALR, BAS, BASR, BRAS (JAS), BRASL (JASL),
BASSM, BSM, SAM24, SAM31, SAM64, TAM. None changes the CC except TAM.

- The machine is fixed in AMODE 31. The link word is bit 32 one and the updated
  instruction address, in R1's low word; the high word is kept. BAL and BALR use this
  format too: their ILC, CC and program-mask format is AMODE 24 only.
- The branch address is read before R1 is written. BALR, BASR and BASSM with R2 = 0
  link without branching.
- BSM sets bit 32 of R1 (when R1 is not 0), then branches to R2 (when R2 is not 0).
- BASSM and BSM branch only into AMODE 31: R2 bit 32 one and bit 63 zero. A target
  selecting AMODE 24 or 64 abends `S0C1` after R1 is written; SAM24 and SAM64 abend
  `S0C1` too (red-dragon-6uyp.75). SAM31 does nothing. TAM sets CC 1.
- The entry R14 (`0xFF0`) has bit 32 off, as in z390, so `BSM 0,14` selects AMODE 24.
  A BASSM or BSM whose target is the activation's return address returns before the mode
  test: nothing runs after it.
- BASR, BALR and BRAS moved here from the seed module; LR moved to load and store.
- z390 models AMODE 24 and 64; its test pins that difference.

**Branch on count and branch on index (red-dragon-6uyp.34).** BCT, BCTR, BCTG, BCTGR,
BRCT (JCT), BRCTG (JCTG); BXH, BXHG, BXLE, BXLEG, BRXH (JXH), BRXHG (JXHG), BRXLE (JXLE),
BRXLG (JXLEG). None changes the CC. BRCTH belongs to the high-word unit.

- The branch address is generated first, then R1 is replaced, wrapped to 32 bits (low word
  only) or 64.
- Count forms subtract one and branch when the result is nonzero. BCTR and BCTGR with R2 = 0
  count without branching.
- Index forms add the increment (R3) and compare the sum, signed, with the compare value
  (R3 + 1 when R3 is even, else R3): BXH forms branch when high, BXLE forms when low or equal.
  Both are read before R1 is written, so R1 = R3 + 1 compares the original value.
- z390 reads BCTR's and BCTGR's R2, and every index form's compare value, after writing R1.
  The z390 test pins BCTR 5,5, BXH 7,6 and BXHG 7,6.

**Storage moves (red-dragon-6uyp.35).** MVC, MVCIN, MVN, MVZ, MVCRL, MVO; MVI, MVIY, MVHHI,
MVHI, MVGHI; MVCL, MVCLE, MVCLU; MVST. Only MVCL, MVCLE, MVCLU and MVST set the CC.

- MVI and MVIY store the immediate byte. MVHHI, MVHI and MVGHI sign-extend the 16-bit
  immediate into 2, 4 or 8 bytes.
- MVC moves L bytes left to right. When the destination starts inside the source, a byte
  loop gives the one-byte-at-a-time result (`MVC A+1(n),A` propagates); otherwise one
  region read and one write move the block. MVN and MVZ always loop, keeping one nibble of
  each destination byte. MVCIN's second address is its rightmost byte.
- MVCRL moves GR0 bits 56-63 plus one bytes, right to left.
- MVO is two byte loops, right to left: the min(L1, L2) bytes with a source byte, each
  fetched once after the bytes to its right are stored, then the rest of the first operand
  from the carry and zeros; the source is truncated on the left.
- MVCL: 24-bit lengths, pad in R2+1 bits 32-39. If the destination starts inside the
  participating source bytes, nothing moves, the lengths are kept and CC is 3; R1 and R2
  only lose bit 32. Otherwise the move completes with CC 0, 1 or 2 from comparing the
  lengths: R1 and R2 advance, R1+1 counts to 0 and R2+1 to the unmoved length. Bits 32-39
  of R1+1 and R2+1 and all high words are kept.
- MVCLE and MVCLU: 32-bit lengths; the pad is the D2(B2) address's low byte (MVCLE) or low
  two bytes, even byte first (MVCLU). No overlap test. MVCLU abends `S0C6` on an odd length.
- MVST copies through the GR0 bits 56-63 character, puts its destination address in R1 and
  sets CC 1; GR0 bits 32-55 nonzero abend `S0C6`.
- Odd pair registers in MVCL, MVCLE and MVCLU abend `S0C6`; che4z and z390 refuse to
  assemble them, so only the unit test reaches it.
- Loop cost: about 8 to 9 VM steps per byte for MVC with overlap and the long-move copy and
  pad, 15 for MVN and MVZ, 4 for the MVCLU pad. MVO costs about 19 per byte, as the unrolled
  form did, plus about 16 to enter its two loops (76 to 92 steps for 3 and 2 bytes, 313 to 333
  for 16 and 16).
- z390 runs MVN and MVZ in 8-, 4-, 2- and 1-byte pieces, so overlap does not propagate; abends
  `S0C1` on MVCLU; and ignores GR0 bits 32-55 in MVST. The z390 test pins all three. z390
  lacks MVCRL.

**Storage compares (red-dragon-6uyp.36).** CLC, CLCL, CLCLE, CLCLU, CLST, CUSE. Unsigned, left to
right: CC 0 equal, 1 first low, 2 first high. Storage is never written.

- CLC reads the two L-byte values as unsigned ints, each in one block (one block per set bit of the length under EX), then tests them equal (CC 0) or orders them (CC 1 or 2); registers unchanged. 34 VM steps at any length.
- CLCL: 24-bit lengths, pad in R2+1 bits 32-39. CLCLE and CLCLU: 32-bit lengths, pad from the
  D2(B2) address (one byte; two for CLCLU, which compares 2-byte characters and abends `S0C6` on
  an odd length). The shorter operand is extended with the pad. With k the offset of the first
  unequal unit, or the longer length when equal, each operand advances by min(k, its length)
  and its length drops by as much. R1 and R2 lose bit 32; CLCL keeps R1+1 and R2+1 bits 32-39.
- CLST: the ending character is GR0 bits 56-63; bits 32-55 nonzero abend `S0C6`. Both ending
  together is CC 0 with R1 and R2 unchanged. An operand that ends first is low. Otherwise R1 and
  R2 point at the last bytes processed.
- CUSE: signed lengths in R1+1 and R2+1 (negative counts as 0 and is kept), substring length
  GR0 bits 56-63, pad GR1 bits 56-63. CC 0 when an equal run reaches the substring length
  (length 0 at once); at the end of the longer operand CC 1 if the last bytes were equal, else 2.
  Each operand advances to the start of the last equal run, at most its own length.
- Units are compared as unsigned ints: one `LoadIndex` per byte, `__binary_bytes_to_int` per CLCLU
  character; the pad and ending character stay ints.
- Loop cost: about 12 VM steps per unit for CLCL, CLCLE, CLCLU and CLST, 10 against the pad, 17
  for CUSE.
- z390 differs: it does not swap the CC when CLCL's first operand is shorter, abends `S0C1` on
  CLCLU, ends CLST with CC 0 and the registers untouched when either operand ends, ignores GR0
  bits 32-55, and reads CUSE's substring length from all of GR0. The z390 test pins each.

**Translate (red-dragon-6uyp.37).** TR, TRT, TRTR, TRE, TROO, TROT, TRTO, TRTT, TRTE, TRTRE.
Tables are read at the table address plus the argument (times two for two-byte functions).

- TR translates L bytes left to right, storing each before the next table fetch, so overlap
  follows the PoO. CC unchanged.
- TRT and TRTR scan until a nonzero function byte, TRTR from the rightmost byte leftward. Found:
  GR2 bits 56-63 get it, GR1 bits 33-63 the byte's address (TRT zeroes bit 32, TRTR keeps it), CC
  1, or 2 at the last byte scanned. None: CC 0, GR1 and GR2 unchanged. Storage is not written.
- TRE translates R1 in place through the R2 table until a byte equals GR0 bits 56-63 (bits 0-55
  ignored): CC 1, else CC 0 at the end. R1 advances and R1+1 counts down by the bytes processed.
- TROO, TROT, TRTO, TRTT translate R2's 1- or 2-byte characters into R1 (R1+1 holds R2's length;
  odd for TRTO or TRTT abends `S0C6`). GR1 is the table, bits 61-63 ignored. A function equal to
  the GR0 test character (bits 56-63, or 48-63 for two-byte functions) stops with CC 1; M3 bit 3
  turns the test off. R2 advances and R1+1 counts down by the source bytes processed, R1 by the
  bytes stored.
- TRTE and TRTRE: M3 A (8) two-byte arguments, odd length `S0C6`; F (4) two-byte functions; L (2)
  with A selects a zero function for arguments over 255 without reading the table. TRTRE's R1 is
  the rightmost argument. Found: R2's low word is the function, R1 its argument's address, R1+1
  the length less the bytes before it, CC 1. End: R2's low word 0, R1 moved by the length, R1+1
  0, CC 0.
- TRE, TROO, TROT, TRTO, TRTT, TRTE and TRTRE clear bit 32 of the R1 and R2 addresses they
  update. Odd R1 in TRE, TROO, TROT, TRTO, TRTT, TRTE and TRTRE
  abends `S0C6`.
- Loop cost: about 10 VM steps per unit for TR, 12 for TRT, TRTR, TRE and TRTE, 13 for TROO, up
  to 15 for the two-byte forms.
- z390 translates one byte in TRE with length 0, abends `S0C6` on a TROO table address off a
  doubleword, and indexes TRTE's two-byte functions by a two-byte argument's low byte. The z390
  test pins all three.

**Execute (red-dragon-6uyp.39, red-dragon-6uyp.79).** EX, EXRL. Ruling R31: a target whose byte 1 is a
data field is lowered once with that field computed in IR; any other target by compile-time
variant expansion (ruling R30).

- The target is found at assembly: EXRL's from its relative operand, EX's from the storage
  operand's address as written (RELOC, no index). The target runs as if it sat at the execute
  instruction, so link information (BAL, BAS, BRAS) points after the EX or EXRL. Relative
  operands arrive resolved, so they stay relative to the target. The CC is the target's.
- R1 = 0, or a target with no lowering, lowers one copy of the target. Otherwise v = (GR R1
  bits 56-63 OR the target's byte 1), kept to the format's operand fields.
- Data fields (R31): an SS-a length code (MVC, MVCIN, MVN, MVZ, CLC, NC, OC, XC, TR, TRT,
  TRTR), SS-b L1/L2 (MVO), an SI or SIY immediate (MVI, MVIY, CLI, CLIY, TM, TMY, NI, NIY, OI,
  OIY, XI, XIY, ASI, AGSI, ALSI, ALGSI), the SVC number, and PLO's R1 and R3 (register numbers read at run time). The target's one lowering takes the
  field as a `DataField`: `WrittenField` for a plain statement, `ExecutedField(v)` under EX.
  The lowering is the same code either way. Only three operations differ by kind, all in the
  field: a span read and a span copy (one block LOAD_REGION/WRITE_REGION for a written length;
  for v, whose length is not a compile-time constant, one block of 2^k bytes for each set bit k
  from 8 down to 0, at offset (length AND NOT (2^(k+1) - 1)), so offsets increase; a read
  joins the blocks as ints; red-dragon-6uyp.81) and a dispatch (a compile-time pick for a written SVC number; equality
  tests on v). Overlap handling is the lowering's, so MVC,
  MVN, MVZ and TR stay byte at a time when destructive.
- Other fields (R30): a binary tree of `<` tests over the values v can reach (the supersets of
  the target's byte) selects one inline copy, lowered through `OPCODE_LOWERINGS` with its
  operands decoded from v. Every copy joins after the tree.
- Byte 1 maps per format and operand shape: SS-a L, SS-b L1/L2, SS-c L1/I3, SS-f L2, SI and SIY
  I2, I (SVC) I, RR R1/R2, RX and RXY R1/X2, RXF R3/X2, RS and RSY R1/R3 or R1/M3, RI and RIL
  R1, the RIE, RIS, RRS, RSI, RSL, SS-e and SSF fields. Unused fields (TS's whole byte) are ignored. Bits that
  are opcode (RI and RIL low nibble; all of RRE, RRF, RRD, S, SIL, SSE, E, IE) abend `S0C1` when R1 sets
  any of them.
- A target that is EX, EXRL, TBEGIN, TBEGINC, TEND or TABORT abends `S0C3`; an odd EX target
  `S0C6`, before R1 is read.
- Size and cost: `EX 2,MOVE` with `MOVE MVC 0(0,3),0(4)` lowers to 140 IR instructions (13,324
  under R30); 16 such sites compile in 0.42 s (40 s under R30). An 80-byte move under EX costs
  75 VM steps (65 under R30); a plain `MVC` of 80 bytes stays at 29. An 80-byte CLC under EX
  costs 141 steps (83 under R30), 314 IR instructions. A plain SVC keeps its one service:
  39 IR instructions against 107 for the chain.
- z390 does not check the odd EX target (it abends `S0C1`), links an executed BRAS after the
  BRAS, and sets CC 1 for an ALSI carry, as it does without EX. The z390 test pins all three.

**Load and store on condition, select, bit counts (red-dragon-6uyp.41).** LOCR, LOCGR, LOCFHR,
LOC, LOCG, LOCFH, LOCHI, LOCGHI, LOCHHI; STOC, STOCG, STOCFH; SELR, SELGR, SELFHR; FLOGR,
POPCNT, CLZG, CTZG, BEXTG, BDEPG. The bridge resolves the extended mnemonics (LOCRE, STOCGNH,
SELFHRO, ...) to the base mnemonic with M3, or M4 for SELECT.

- On condition: the M3 bit `8 >> CC` decides whether the move happens; the test comes first, so
  nothing is read or written otherwise. LOC, LOCR, LOCHI and STOC use the low word, LOCFH,
  LOCFHR, LOCHHI and STOCFH the high word, the G forms the whole register; the other half is
  kept. I2 is a signed halfword. The Principles of Operation leave an access exception on an
  unmet condition model dependent; none is raised. CC unchanged.
- SELECT reads R2 and R3, writes R3 to R1, then R2 if M4 selects the CC. SELR uses low words,
  SELFHR high words, SELGR whole registers. CC unchanged.
- FLOGR: R1 gets the leftmost one's position, or 64; R1+1 gets R2 with that bit cleared; CC 0
  none found, 2 found. An odd R1 abends `S0C6`; che4z refuses one at assembly. POPCNT counts each
  byte, or all 64 bits when M3 bit 0 is on; CC 0 zero, 1 not. CLZG and CTZG count leading and
  trailing zeros, 64 for zero; CC unchanged.
- BEXTG packs R2's bits under the R3 mask left-justified; BDEPG deposits R2's leftmost n bits (n
  the mask's ones) at the mask's ones, in order. Both zero the rest; CC unchanged.
- The counts are branch-free IR (SWAR population, a right smear for the leading zeros and the
  leftmost one). BEXTG and BDEPG loop once per one bit of the mask, right to left, about 22 VM
  steps each, moving one bit between that mask bit and a cursor that starts at 2^(64 - n).
- The NE/NZ, NL/NM and NH/NP suffixes are 7, 11 and 13 (Figure J-1). Our che4z fork corrects
  LOC, LOCG, LOCR, LOCGR, STOC and STOCG, which upstream che4z encodes as 6, 10 and 12 (ruling
  R32, red-dragon-6uyp.82).
- z390 does not execute LOCHI, LOCGHI, LOCHHI, LOCFHR, LOCFH, STOCFH, CLZG, CTZG, BEXTG or BDEPG
  (`S0C1`), and SELFHR moves the whole register. The z390 test pins both; those expectations
  come from the Principles of Operation.

**Interlocked update (red-dragon-6uyp.42).** CS, CSY, CSG, CDS, CDSY, CDSG; CAL, CALGF, CALG;
CSST; LAA, LAAG, LAAL, LAALG, LAN, LANG, LAO, LAOG, LAX, LAXG; LPD, LPDG, LPQ, STPQ; TS; PLO. One CPU
(ruling R33): nothing models a lock or another CPU.

- A misaligned operand abends `S0C6` before anything changes. Operands must sit on their own size
  (word, doubleword, quadword), except TS, which has no boundary, and CAL's second operand, which
  is checked only when the compare is equal. An odd register of a pair form abends `S0C6`; che4z
  refuses one for CDS*, LPD*, LPQ and STPQ, so only the unit test reaches it.
- CS, CSY, CSG compare R1 with storage; CDS, CDSY the low words of R1 and R1+1 as 64 bits, CDSG the
  pair as 128 bits. Equal: storage ← R3 (or its pair), CC 0. Unequal: R1 ← storage, CC 1.
- CAL, CALGF, CALG compare the first operand with R3. Equal: R3 ← the second operand, CC 0;
  unequal: R3 ← the first, CC 1. CAL works on low words; CALGF compares words and loads R3 whole
  (a doubleword, or the word zero-extended); CALG doublewords. The second operand's boundary is
  checked only when it is loaded (the PoO leave the unequal case to the model).
- CSST: GR0 bits 56-63 the function code (0 word, 1 doubleword, 2 quadword with R3 even), bits
  48-55 the store characteristic (2^SC bytes, 0-4), GR1 bits 33-59 the parameter list. Equal: the
  replacement (list bytes 0-15) goes to op1, then the leftmost 2^SC bytes of the store value (from
  byte 16) to op2, CC 0. Unequal: R3 ← op1, CC 1. An unassigned code, op1 or op2 off its boundary,
  or an odd R3 with code 2 abends `S0C6`, whatever the comparison.
- LAA, LAAL, LAN, LAO, LAX and their G forms: op2 ← op2 OP R3, then R1 ← the old op2. The CC is
  that of AR, ALR, NR, OR or XR; LAA and LAAG take the `S0C8` check after both stores.
- LPD and LPDG load R3 and R3+1 (low words or whole) and set CC 0. LPQ and STPQ move a quadword to
  or from the R1 pair; CC unchanged. TS sets CC from bit 0 of the byte, then stores X'FF'.
- PLO: GR0 bits 32-54 nonzero abend `S0C6`. With the test bit (55) on, CC 0 for function codes
  0-61 and 3 otherwise, and nothing else happens. Otherwise a code over 61 abends `S0C6`, and a
  tree of `<` tests picks one block per code. The PLO-extension facility (z17) makes 0-61 valid
  and leaves GR1 unused. Each block comes from a row of `LOCKED_OPERATIONS`, one per code from
  Figure 7-380: width, compares, stores in order, boundary checks, even registers and the list
  offsets of its operand addresses. R1 and R3 are register numbers at run time, so EX of PLO
  lowers once. A register form with an odd R1 (codes 4-22) or R3 (8, 10) abends `S0C6`. D2 (codes
  0-29), D4 as an operand, the parameter list (a doubleword) and every address held in the list
  (bits 33-63) are checked before any compare or store, so an `S0C6` changes nothing. Compares are
  unsigned and run in order. The first unequal one replaces its comparison value with the operand
  and sets CC 1, CC 2 for DCS's second, or CC 2 with the unequal-results byte (list byte 48) set
  to its number for codes 30-37. All equal: the stores run in the Principles of Operation order
  and CC 0. Codes 38-61 only load or store and leave the CC.
- PLO lowers to about 7,300 IR instructions per statement and compiles in about 1.2 s
  (red-dragon-6uyp.83).
- z390 does not execute CAL, CALGF, CALG, CSST or PLO (`S0C1`; one CSST case `S0C5`), checks no
  boundary in CS, CSG, CDSG, LPD, LPDG, LPQ and STPQ, and sets LAAL's CC from a stale operand
  (CC 3 for a zero sum with carry). The z390 test pins each; those expectations come from the
  Principles of Operation.

**Unicode conversion and string search (red-dragon-6uyp.43).** CU12, CU14, CU21, CU24, CU41,
CU42, CUTFU, CUUTF, SRST, SRSTU. CUTFU and CUUTF reach the lowering as their own mnemonics and
lower as CU12 and CU21.

- The conversions take R1 and R2 as even pairs (odd: `S0C6`), lengths in R1+1 and R2+1. Each
  character converts in turn, in one execution: CC 0 when R2 cannot hold the next character
  (judged from its lead unit), CC 2 at an invalid one with R2 at it, CC 1 when R1 cannot hold the
  result. CC 2 beats CC 1. Both pairs then advance and count down; addresses lose bit 32.
- M3 bit 3 (W) turns on well-formedness checks for CU12, CU14, CU21 and CU24. UTF-8 without W:
  80-BF and F8-FF are invalid leads, continuation bits 0-1 are ignored. With W: C0, C1 and F5-F7
  too, continuations must be 80-BF, three-byte values 800-FFFF but not D800-DFFF, four-byte
  10000-10FFFF. UTF-16 with W: a high surrogate needs a low one after it, and an isolated low
  surrogate is invalid. UTF-32 D800-DFFF and values over 10FFFF are always invalid.
- Model choices (z17): isolated low surrogates with W and UTF-32 DC00-DFFF are invalid; the PoO
  let older models convert them.
- A four-byte UTF-8 character or a surrogate pair becomes a UTF-16 pair (zabcd = uvwxy - 1, z
  dropped) or four UTF-8 bytes, so an overlong four-byte UTF-8 without W still yields a pair.
- SRST and SRSTU search from R2 while the unit starts below R1. GR0 bits 32-55 (SRST) or 32-47
  (SRSTU) nonzero abend `S0C6`. Found: R1 is its address, bit 32 zero, CC 1. Otherwise CC 2 and
  both registers unchanged; R1 = R2 is CC 2 at once.
- z390 abends `S0C1` on every conversion and on SRSTU; its SRST matches. The z390 test pins the
  `S0C1`s.

**High word (red-dragon-6uyp.44).** AHHHR, AHHLR, SHHHR, SHHLR, AIH; ALHHHR, ALHHLR,
SLHHHR, SLHHLR, ALSIH, ALSIHN; CHHR, CHLR, CHF, CIH, CLHHR, CLHLR, CLHF, CLIH, CLMH; LBH, LHH,
LLCH, LLHH, LFH, LFHAT, STCH, STHH, STFH, LMH, STMH, ICMH, STCMH; BRCTH (JCTH). They work on bits
0-31 of a register and never write R1's low word.

- The register forms take R2's high word; `..HHR` takes R3's high word, `..HLR` its low word.
  CHLR and CLHLR compare R1's high word with R2's low word.
- The arithmetic and compares reuse the low-word builders with high-word sources and sink.
  ICMH, STCMH, CLMH, LMH, STMH and BRCTH reuse ICM, STCM, CLM, LM, STM and BRCT with a
  `RegisterPart` (low word, high word or whole register). The signed forms set CC 3 on
  overflow and take the `S0C8` check after the store.
- ALSIH adds a signed 32-bit immediate as a logical add, so a negative one sets the CC as a
  subtract would and never CC 0. ALSIHN stores the same sum and leaves the CC.
- LFHAT loads, then abends `S0C7` if the word is zero, like LAT.
- No form has a data field in byte 1, so EX expands their variants (ruling R31).
- z390 abends `S0FF` on LFHAT of zero (as for LAT) and reports a borrow as a carry for ALSIH with
  a negative immediate (as for ALSI). The z390 test pins both.

**Miscellaneous (red-dragon-6uyp.45).** SPM, IPM, EPSW; CPYA, EAR, SAR, LAM, LAMY, STAM, STAMY;
CKSM; STCK, STCKF, STCKE, ECTG; ECAG, STFLE, LCBB; MC, NIAI, PFD, PFDRL, TRAP2, TRAP4. SVC is
its own module.

- SPM sets the CC from R1 bits 34-35 and the program mask from 36-39. IPM zeroes R1 bits 32-33
  and puts the CC and mask in 34-39. EPSW builds a fixed problem-state PSW (ruling R37): R1's
  low word gets X'0785' in bits 0-15, the CC and mask in 18-23, EA 0; then, if R2 is not 0, R2's
  low word gets X'80000000' (BA).
- Access registers (ruling R35) hold values only: CPYA, EAR and SAR move a word; LAM, LAMY, STAM
  and STAMY wrap from 15 to 0 and abend `S0C6` off a word boundary before any access.
- CKSM (ruling R28): R2 even, else `S0C6`. Adds the words at R2 for R2+1's length, the last
  padded with zeros, into R1's low word with an end-around carry; R2 advances (bit 32 cleared),
  R2+1 becomes 0, CC 0.
- Clocks (ruling R36): `__hlasm_tod_clock` returns the 104-bit TOD clock and `__hlasm_cpu_timer`
  the CPU timer, read from a `MachineClock` given to `clock_builtins`; a builtin because a
  clock reads outside the program. STCK and STCKE are unique and in execution order (PoO
  4-51): `__hlasm_tod_last` keeps the last one as a 104-bit value, an STCK value extended
  with 40 zeros. STCK stores clock bits 0-63, raised to one above the last value's bits
  0-63 if not later. STCKE stores epoch 0, the 104 bits with bit 103 on, raised to one above
  the last value (bit 103 kept on) if not later, and a zero programmable field. STCKF stores
  clock bits 0-63 and is not ordered. All set CC 0. ECTG
  fetches its three operands, then GR0 ← first − CPU timer, GR1 ← second, R3 ← third.
- ECAG (ruling R37) returns constants, z17-like rather than published: cache topology
  X'04070B0B00000000', 256-byte lines, 128 KiB, 36 MiB, 360 MiB and 2,880 MiB, 8, 18, 48
  and 48 ways (I and D alike), 5,500 cycles per microsecond. Reserved bits 40-53, a reserved
  ASI, AI or level give all ones.
- STFLE stores the list X'E1003F63F47C8C24', X'0000890000000000': a bit is on when the
  facility's problem-state instructions are all lowered. The floating-point bits are on: 20,
  23, 37, 41, 42, 43 (DFP high performance, as 19 is for long displacement), 44, 48 and 80.
  The vector bits (129, 134, 135, 148, 152, 192, 198, 199) each imply 129, and some imply others. They turn on
  together at the end of wave 2, so 129 is off although LCBB is lowered. 16 and 24 wait for
  PKA, PKU, UNPKA and UNPKU, 49 for PPA. It stores min(GR0 bits 56-63 + 1, 2) doublewords,
  sets those bits to 1, and sets CC 0, or 3 when the list was cut short. Off a doubleword it
  abends `S0C6`.
- LCBB: R1's low word ← bytes to the next 64 << M3 boundary, at most 16; CC 0 at 16, else 3.
  M3 over 6 abends `S0C6`.
- MC abends `S0C6` when I2 bits 0-3 are not zero; with the monitor masks off (CR8 = 0) it
  does nothing else. Its I2 is a data field, so EX lowers it once (ruling R31). NIAI, PFD
  and PFDRL lower to nothing (ruling R38). TRAP2 and TRAP4 abend `S0D3`: no trap control is
  enabled, a special-operation exception.
- SPM with program-mask bit `1000` makes every signed overflow abend `S0C8`; the tests run AR,
  AGR, LCR, LCGR, LPR, LPGR, MSC, MSRKC, MSGC, MSGRKC, SLA, SLAK, SLAG, SLDA, AHHHR, AIH, LAA
  and LAAG that way against z390.
- z390 abends `S0C1` on CKSM, EPSW, ECAG, LCBB and MC and `S0C5` on ECTG; leaves the CC after
  STCK and STCKE; stores zeros for STCKE's bits 64-103 and does not order STCKE against STCK
  or STCKE; stores one doubleword for STFLE with
  CC 0, GR0 unchanged and no boundary check; does not check LAM and STAM boundaries; and starts
  the access registers at F4F4F4F4. The z390 test pins each.

**Packed-decimal arithmetic (red-dragon-6uyp.46).** AP, SP, ZAP, MP, DP, SRP. Ruling R39.

- Each operand is read in one IR loop into a magnitude, a negative bit (sign B or D) and an
  invalid bit (a digit A-F or a sign 0-9). Every operand is read and checked before the first
  store, so overlapping operands act as if processed right to left. Results carry sign C or D.
- AP, SP, ZAP and SRP set CC 0, 1 or 2 from the result, 3 on overflow. A zero result is
  positive unless it overflowed, when it keeps the true sign. Overflow stores the low digits,
  sets CC 3, then abends `S0CA` when program-mask bit `0100` is on, as it is at start.
- Any invalid code abends `S0C7` with nothing stored; ZAP checks only its second operand.
  AP, SP, MP and DP operands that overlap without coincident rightmost bytes always put a
  sign in a digit position or a digit in the sign position, so that check catches improper
  overlap. ZAP with its first operand ending left of the second fetches the whole second
  operand first, one of the two behaviours the Principles of Operation allow.
- MP and DP abend `S0C6` when L2 is over 8 bytes or not below L1. MP abends `S0C7` when the
  multiplicand has fewer leftmost zero bytes than the multiplier has bytes. DP abends `S0CB`
  when the divisor shifted left by the quotient's digits is not above the dividend (the
  Principles of Operation's trial comparison; a zero divisor included). The product and
  quotient signs follow algebra and the remainder takes the dividend's, zeros included. CC
  unchanged.
- SRP shifts by bits 58-63 of the second-operand address, signed. A right shift adds I3 to
  the leftmost digit shifted out of the magnitude, so a negative rounds away from zero. I3
  above 9 abends `S0C7` even when nothing rounds.
- EX (ruling R31) lowers each once: L1 and L2 are byte 1, and so are SRP's L1 and I3.
- z390 rounds a negative SRP toward zero, ignores an invalid I3, loses negative zeros (MP
  products, DP quotients and remainders) and shows CC 0 at an `S0CA`. The z390 test pins each.

**Packed-decimal compare and test (red-dragon-6uyp.47).** CP, TP. Rulings R29, R31, R34, R39.

- CP reads and checks both operands (1-16 bytes each), abending `S0C7` with the CC unchanged
  on any invalid digit or sign. It then compares the signed values as ints: CC 0 equal, 1
  first low, 2 first high. -0 equals +0, and alternate signs equal preferred ones.
- TP (RSL-a) never abends for its data. CC 0 all valid, 1 only the sign invalid, 2 only a
  digit invalid, 3 both.
- Neither stores and neither has a specification exception. EX (ruling R31) lowers each
  once: CP's L1 and L2 and TP's L1 (`LENGTH_HIGH_NIBBLE`) are byte 1; TP's bits 12-15 are
  unassigned and ignored.
- z390 agrees on every case.

**Decimal conversion (red-dragon-6uyp.48).** CVB, CVBY, CVBG, CVD, CVDY, CVDG, PACK, PKA, PKU,
UNPK, UNPKA, UNPKU. Rulings R1, R29, R31, R34, R39.

- CVB and CVBY read 8 packed bytes, CVBG 16, abending `S0C7` on an invalid code with R1
  unchanged. A CVB or CVBY result outside 32 bits puts its low 32 bits in R1's low word, then
  abends `S0C9`; CVBG outside 64 bits abends `S0C9` with R1 unchanged. -0 converts to 0.
- CVD and CVDY take R1's low word, CVDG all 64 bits, and store 8 or 16 bytes with sign C or
  D. A binary zero is +0, so no negative zero arises. The CC is unchanged throughout.
- PACK and UNPK check nothing. Each result byte is stored right after its source bytes are
  fetched, right to left, so overlapping operands behave as the Principles of Operation
  describe; UNPK fetches a source byte once for two result bytes. The rightmost byte swaps its
  nibbles. Source bytes left of the operand read as zero; extra source digits are dropped.
- PKA and PKU store 16 bytes with sign C, taking the low four bits of each byte or two-byte
  character; a 32-character source loses its leftmost. UNPKA and UNPKU unpack 16 bytes into
  ASCII or Unicode digits; a 32-character result gets a zero leftmost. They set CC 0 for sign
  A, C, E or F, 1 for B or D and 3 otherwise; digits are not checked and nothing abends
  `S0C7` (the Principles of Operation, chapter 8). L2 over 32 bytes (PKA), L1 over 32 bytes
  (UNPKA), or over 64 or odd (PKU, UNPKU) abends `S0C6` before any store.
- EX (ruling R31) lowers each storage form once: PACK and UNPK on `LENGTH_NIBBLES`, PKA and
  PKU on `SECOND_LENGTH_BYTE`, UNPKA and UNPKU on `LENGTH_BYTE`.
- z390 suppresses an out-of-range CVB and CVBY instead of storing the low word, stores a stale
  value for CVDY, and abends `S0C1` on PKU and UNPKU. The z390 test pins each.

**Edit (red-dragon-6uyp.49).** ED, EDMK. Rulings R29, R31, R34, R39.

- The pattern is edited left to right one byte at a time. Byte 0 is the fill byte, read
  first, then processed like any other. X'20' and X'21' take the next source digit: the
  pending right nibble of the last source byte if it is a digit, else the left nibble of a
  newly fetched byte. Significant digits become zoned (`F0`-`F9`); a zero digit with the
  significance indicator off becomes the fill byte. X'22' becomes the fill byte and ends the
  field; message bytes stay when the indicator is on, else become the fill byte.
- The indicator turns on at a nonzero digit or at X'21', and off at X'22' or after a
  fetched byte whose right nibble is a plus code (A, C, E, F). B and D leave it alone.
- CC 0 when the last field is zero or has no digits, else 1 with the indicator on and 2
  with it off.
- A left nibble A-F abends `S0C7`. The Principles of Operation leave suppression or
  termination to the model; we suppress (ruling R34): a first walk over the pattern reads
  and checks the source digits, then a second one edits. Pattern, CC and GR1 stay unchanged.
  Right nibbles are never invalid.
- EDMK puts the address of the rightmost digit made significant by itself (indicator off,
  digit nonzero) in GR1 bits 33-63, bit 32 zero, bits 0-31 kept. A digit forced
  significant by X'21' sets nothing, so GR1 can stay unchanged.
- Overlapping pattern and source are unpredictable by the Principles of Operation; each
  source byte is read when needed and each pattern byte before it is written.
- EX (ruling R31) lowers each once on `LENGTH_BYTE`.
- z390 agrees on every case.

**Floating-point support (red-dragon-6uyp.50).** CPSDR, EFPC, LCDFR, LD, LDGR, LDR, LDY, LE,
LER, LEY, LFAS, LFPC, LGDR, LNDFR, LPDFR, LXR, LZDR, LZER, LZXR, SFASR, SFPC, SRNM, SRNMB,
SRNMT, STD, STDY, STE, STEY, STFPC. PFPO is in .56 (ruling R42). Rulings R34, R37, R41.

- FPR f is bytes 0-7 of vector register f in `__hlasm_vrs`; `__hlasm_fpc` is the FPC. Both
  start at 0. AFP control is on, so every FPR is usable. All forms are bit moves in IR; none
  sets the CC.
- Short forms (LE, LEY, LER, LZER, STE, STEY) use FPR bits 0-31 and leave bits 32-63 alone.
  LXR and LZXR use pairs (r, r+2); an R with bit value 2 set abends `S0C6`.
- LCDFR, LNDFR and LPDFR flip, set and clear bit 0; CPSDR R1,R3,R2 takes R2 with R3's sign.
- SFPC and LFPC (and LFAS, SFASR) abend `S0C6` with the FPC unchanged when bits 6-7, 14-15,
  24 or 28 are set or the BFP mode is 4-6. The PoO calls this a specification exception;
  ruling R41's `S0C7` is not used. SRNM sets bits 30-31 and clears 29; SRNMB sets 29-31 and
  abends `S0C6` on address bits 56-60 or mode 4-6; SRNMT sets 25-27.
- LFAS and SFASR OR the old flags (byte 1 bits 0-5, as Figure 9-21 has the quantum flag;
  SFASR's text says 0-4) into the loaded flags. When an old flag meets a loaded mask the FPC
  is stored with Figure 9-21's DXC in byte 2, then the run abends `S0C7`.
- z390 starts the FPC at X'70000000', clears bits 32-63 on short loads, routes the sign forms
  through an HFP value (`S0C7` or lost bits), checks no pair or FPC value and never signals
  from LFAS or SFASR. The z390 test pins each (red-dragon-6uyp.74).

**BFP arithmetic (red-dragon-6uyp.51).** ADB, ADBR, AEB, AEBR, AXBR, CDB, CDBR, CEB, CEBR,
CXBR, DDB, DDBR, DEB, DEBR, DIDBR, DIEBR, DXBR, FIDBR, FIDBRA, FIEBR, FIEBRA, FIXBR, FIXBRA,
KDB, KDBR, KEB, KEBR, KXBR, LCDBR, LCEBR, LCXBR, LNDBR, LNEBR, LNXBR, LPDBR, LPEBR, LPXBR,
LTDBR, LTEBR, LTXBR, MADB, MADBR, MAEB, MAEBR, MDB, MDBR, MDEB, MDEBR, MEEB, MEEBR, MSDB,
MSDBR, MSEB, MSEBR, MXBR, MXDB, MXDBR, SDB, SDBR, SEB, SEBR, SQDB, SQDBR, SQEB, SQEBR,
SQXBR, SXBR, TCDB, TCEB, TCXB. Rulings R34, R41, R43.

- IR splits each operand into sign, biased exponent and fraction and hands the list to a
  `bfp_builtins()` builtin over `zarch_float`; IR encodes the fields it returns. The
  rounding code is the M field, or the FPC's BFP mode as `(mode + 4) & 7`.
- Trap ladder: an enabled invalid or division-by-zero condition sets the DXC and abends
  `S0C7` with nothing stored. An enabled overflow or underflow (tininess) stores the scaled
  result, sets DXC 2x or 1x, and abends. Otherwise the result is stored, the unenabled flags
  are ORed into FPC byte 1, and an enabled inexact sets DXC 08 or 0C and abends.
- CxB, KxB and TCxB are IR on the image (ruling R44): a NaN is a magnitude above the
  infinity image, ordering compares magnitude times (1 - 2 x sign), and TCxB picks mask bit
  11 - 2 x class - sign. CxB signals on an SNaN, KxB on any NaN, through the ladder.
- CC: add, subtract and the sign forms from the stored image; compares from the order, or 3
  when unordered; DIxBR per Figure 19-22 (final when |q| < 2^p or q is an integer, since
  past 2^p the two nearest integers are not both representable); TCxB 0 or 1. The rest
  leave it.
- Short results replace FPR bits 0-31 only. Extended operands use pairs (r, r+2). An invalid
  pair, an M3 or M4 of 2 or 8-15, or DIxBR registers that are not distinct abend `S0C6` at
  compile time. FIxBRA M4 bit 1 suppresses inexact.
- LCxBR, LNxBR and LPxBR change the sign bit in IR and never signal. LTxBR quiets an SNaN
  and raises invalid through the same ladder.
- z390 writes X'F4F4F4F4' into bits 32-63 of some short results, rounds the fused product,
  gives CC 1 for unordered compares and NaN sign forms, ignores the round-toward-minus sign
  of an exact zero sum, multiplies extended inexactly, rejects AXBR R1 = 1 and any FIxBRA or
  DIxBR modifier, does not quiet LTDBR's SNaN, picks other fused NaNs, misclassifies
  subnormals, infinities, NaNs and -0 in TCDB, and takes no invalid or inexact trap. The z390 test pins each (red-dragon-6uyp.74).

**BFP conversions (red-dragon-6uyp.52).** CDFBR, CDFBRA, CDGBR, CDGBRA, CDLFBR, CDLGBR,
CEFBR, CEFBRA, CEGBR, CEGBRA, CELFBR, CELGBR, CFDBR, CFDBRA, CFEBR, CFEBRA, CFXBR, CFXBRA,
CGDBR, CGDBRA, CGEBR, CGEBRA, CGXBR, CGXBRA, CLFDBR, CLFEBR, CLFXBR, CLGDBR, CLGEBR,
CLGXBR, CXFBR, CXFBRA, CXGBR, CXGBRA, CXLFBR, CXLGBR, LDEB, LDEBR, LDXBR, LDXBRA, LEDBR,
LEDBRA, LEXBR, LEXBRA, LXDB, LXDBR, LXEB, LXEBR. Rulings R43-R45.

- To fixed and to logical round through a `to_fixed_32/64` or `to_logical_32/64` builtin and
  the .51 ladder. The builtin returns the integer's image and the CC: 3 when invalid, else
  0, 1 or 2 by the source, so -0.5 rounded to 0 gives CC 1. A 32-bit result replaces bits
  32-63 of R1.
- A NaN or out-of-range source is invalid: enabled, `S0C7` with R1 and the CC unchanged;
  masked, the maximum of the source's sign (signed; a NaN gives the negative one) or 0 or
  the unsigned maximum (logical), CC 3, the invalid flag, and inexact (flag or DXC 08).
- From fixed rounds through the `from_fixed` builtin when the target is narrower than the
  integer (short from either width, long from 64 bits); otherwise it is exact and IR
  (ruling R45): sign, the leading one from `bit_counts.leading_zeros`, a rebased exponent
  and the left-justified fraction. A 32-bit source is bits 32-63 of R2.
- LDEB(R), LXDB(R) and LXEB(R) are exact and IR: a finite source goes through the same
  exact encoding, so a subnormal becomes normal; infinities and NaNs keep the fraction
  shifted left. An SNaN raises invalid through the ladder: suppressed, or quieted.
- LEDBR, LDXBR and LEXBR (and the A forms) round through a `rounded_to_short/long`
  builtin. The nontrap result replaces only the target's bits of R1; an enabled overflow or
  underflow stores the scaled result in the source format (Figure 19-9), so the lowering
  always writes the source-format image, the rounded one merged over R1's old bits.
- M3 of 2 or 8-15, or an extended operand that is not a pair, abends `S0C6`. M4 bit 1
  suppresses inexact on the A forms and the logical forms.
- z390 rejects a nonzero M4, ignores the FPC mode, wraps or loses bits out of range, gives
  CC 0 for -0.5 to 0 and for -infinity, converts -1 to logical 1, abends `S0C5` on a NaN
  and takes no inexact trap. From fixed it ignores M3, writes X'F4F4F4F4' into bits 32-63 of
  short results and garbles logical sources and extended low halves. Between formats it
  ignores M3, loses bits lengthening a subnormal, abends `S0C5` lengthening an infinity or
  NaN to extended and takes no LOAD ROUNDED trap. The z390 test pins each
  (red-dragon-6uyp.74).

**HFP arithmetic (red-dragon-6uyp.53).** AD, ADR, AE, AER, AU, AUR, AW, AWR, AXR, CD, CDR,
CE, CER, CXR, DD, DDR, DE, DER, DXR, FIDR, FIER, FIXR, HDR, HER, LCDR, LCER, LCXR, LNDR,
LNER, LNXR, LPDR, LPER, LPXR, LTDR, LTER, LTXR, MAD, MADR, MAE, MAER, MAY, MAYH, MAYHR,
MAYL, MAYLR, MAYR, MD, MDE, MDER, MDR, ME, MEE, MEER, MER, MSD, MSDR, MSE, MSER, MXD, MXDR,
MXR, MY, MYH, MYHR, MYL, MYLR, MYR, SD, SDR, SE, SER, SQD, SQDR, SQE, SQER, SQXR, SU, SUR,
SW, SWR, SXR. Rulings R34, R39, R41, R46.

- IR splits each operand into sign, characteristic and fraction and hands the list to an
  `hfp_builtins()` builtin over `zarch_float`; IR encodes what it returns. Compare uses the
  same normalized subtraction, so it is a builtin too; it returns the CC.
- Program-mask ladder: an HFP divide abends `S0CF` and a negative square root `S0DD`
  (PIC 001D), both with nothing stored. Otherwise the result is stored with its
  characteristic modulo 128, or a true zero when underflow or significance is raised with
  its mask bit (0010, 0001) off. Then overflow abends `S0CC`, and underflow and
  significance abend `S0CD` and `S0CE` when their mask bits are on. Each operation emits only
  the checks it can raise (`RAISES`), so MY, MAY and FIxR call and store with no ladder.
- Extended results set the low-order sign to the high-order sign and its characteristic to
  the high one minus 14 modulo 128, or 0 for a true zero. MY and MAY wrap both
  characteristics even for a zero fraction.
- CC: add, subtract and the sign forms give 0 for a zero fraction, else 1 or 2 by sign;
  compare gives 0 when the difference with its guard digit is zero. The rest leave it.
- Short results replace FPR bits 0-31 only. Extended operands use pairs (r, r+2); MXD, MXDR,
  MY and MYR check R1 only; MAY and MAYR take any R1, write the pair holding it and use R1
  itself as the addend. An invalid pair abends `S0C6` at compile time.
- LT, LC, LN and LP change the sign in IR. Short and long images keep their characteristic;
  an extended zero fraction becomes a true zero with the new sign.
- z390 writes X'F4F4F4F4' into bits 32-63 of some short results, rounds or uses host floating
  point where HFP truncates (SDR, SWR, SW, MD, MXDR, MSE, SQD), ignores the guard digit in
  unnormalized subtraction and COMPARE, drops the sign of MY, MYH and MYL, makes a zero MY
  product, LTDR and LCDR of a zero fraction a true zero, rejects MAY R1 = 6, garbles MAYH and
  MAYL, stores a nonzero value for a masked underflow, and abends `S0C7` for a negative
  square root. The z390 test pins each (red-dragon-6uyp.74).

**HFP conversions (red-dragon-6uyp.54).** CDFR, CDGR, CEFR, CEGR, CFDR, CFER, CFXR, CGDR,
CGER, CGXR, CXFR, CXGR, LDE, LDER, LDXR, LEDR, LEXR, LRDR, LRER, LXD, LXDR, LXE, LXER, TBDR,
TBEDR, THDER, THDR. Ruling R47.

- To fixed and to BFP round by M3 through a `to_fixed_32/64` or `to_bfp_short/long`
  builtin. There is no ladder: neither raises a program check. M3 0 truncates; the FPC mode
  is not used. M3 3 is valid only for TBxDR. Any other M3, or an extended R2 that is not a
  pair, abends `S0C6`.
- The CC comes from the source: 0 for a zero fraction, else 1 or 2 by sign, so 0.3 rounded
  to 0 gives CC 2. CC 3 means out of range (to fixed: the maximum of the source's sign) or
  overflow (to BFP: infinity or Nmax by method, figure 9-20). A tiny TBEDR source is
  denormalized and keeps CC 1 or 2.
- From fixed and BFP to HFP are IR (no rounding method): `hfp_ir.normalized_fields` takes a
  sign, a magnitude and a binary exponent, counts leading zeros and gives the characteristic
  and the hex-normalized fraction, truncated. From fixed leaves the CC; zero is a positive
  true zero. THDxR is exact; a zero keeps its sign (CC 0); a characteristic below 0 gives a
  zero of the source's sign (CC 1 or 2); above 127, or an infinity, gives all ones with the
  source's sign, and a NaN gives +all ones (CC 3, figure 9-18).
- LOAD LENGTHENED is IR: the fraction gains zeros. Long keeps the characteristic, even for a
  zero fraction. Extended gives a true zero of the source's sign for a zero fraction (so LXDR
  of -0 is -0 in both halves), else the usual low-order part.
- LOAD ROUNDED is IR: add one at the first dropped bit, shift right a digit on a carry, no
  normalization. A characteristic past 127 is stored modulo 128, then `S0CC`. Short results
  replace bits 0-31; LDXR and LRDR write one FPR. Pairs: R1 of LXxR/LXx, CXFR and CXGR, R2 of
  LDXR, LRDR and LEXR.
- z390 sets the to-fixed CC from the result, wraps out-of-range sources, writes X'F4F4F4F4'
  into bits 32-63 of TBEDR results, flushes tiny TBEDR values to +0 with CC 0, gives CC 2 on
  overflow and garbles TBDR. It rounds CEFR and CDGR, converts BFP to HFP through host floating
  point (losing low bits, a signed zero and the THDR overflow result) and abends `S0C5` for
  THDER of an infinity. It drops the sign of LXDR -0, zeroes the LXD low characteristic, keeps the
  characteristic of an extended zero fraction, truncates LEDR, LRER and LDXR, and takes no
  LOAD ROUNDED overflow. The z390 test pins each (red-dragon-6uyp.74).

**DFP arithmetic (red-dragon-6uyp.55).** ADTR, ADTRA, AXTR, AXTRA, CDTR, CEDTR, CEXTR, CXTR,
DDTR, DDTRA, DXTR, DXTRA, EEDTR, EEXTR, ESDTR, ESXTR, FIDTR, FIXTR, IEDTR, IEXTR, KDTR,
KXTR, LTDTR, LTXTR, MDTR, MDTRA, MXTR, MXTRA, QADTR, QAXTR, RRDTR, RRXTR, SDTR, SDTRA, SLDT,
SLXT, SRDT, SRXT, SXTR, SXTRA, TDCDT, TDCET, TDCXT, TDGDT, TDGET, TDGXT. Rulings R34, R41, R43, R44, R49.

- Each operand goes through the format's decode IR function to `[negative, e, significand]`
  (`e` the biased exponent, or -1 infinity, -2 QNaN, -3 SNaN); a `dfp_builtins()` builtin
  rounds; the encode IR function builds the canonical result image after delivery.
- Rounding: M4 0 or 2 (and the non-A forms) take the FPC DFP mode, bits 25-27, as code
  `mode + 8`; 1 and 3-15 are the modifier. M4 0 or 8-15 suppress the quantum exception.
- The trap ladder is the BFP one, with a DFP-only step first (`dfp_ir.quantum_yields`): the
  quantum exception (mask and flag X'04', DXC 04) completes after the store, and is not
  recognized when an inexact trap is taken. BFP IR carries no quantum step.
- CC: add and subtract per figure 20-10, 3 for a NaN; multiply and divide leave it.
- FIxTR, QAxTR and RRxTR call builtins. FIxTR rounds and sets XqC by M3; M4 bit 1 (X'4')
  suppresses inexact. QAxTR takes the quantum from R2 and the value from R3; RRxTR the
  significance from GR R2 bits 58-63. Their quantum exception compares the result's quantum
  with the third operand's.
- CxTR and KxTR are IR (ruling R50): both coefficients scale to the lower exponent, an
  infinity ranks beyond any finite value, a NaN gives CC 3; CxTR signals on an SNaN, KxTR on
  any NaN.
- Also IR on the decoded fields (R44): CExTR compares `e` for finite operands, infinities equal,
  NaNs equal, other mixes CC 3; EExTR stores `e` in a GR; ESxTR the significant digits (0 for
  zero) or `e`; IExTR takes GR R2 signed, keeping 0..MBE, -1 and -3 and making anything else
  a QNaN, with the third operand's sign and digits; LTxTR canonicalizes, drops an infinity's
  digits and quiets an SNaN through the ladder.
- SLxT and SRxT shift by EA bits 58-63: all digits of a finite number, the trailing digits of
  an infinity or NaN; the exponent and kind stay.
- TDCxT and TDGxT select mask bit 11 - (2 x class or group + sign) of EA bits 52-63. Subnormal
  is nonzero below Nmin; extreme is e 0 or MBE; a subnormal with a nonextreme exponent is
  safe nonzero (allowed by 20-57).
- z390 encodes zero results with biased exponent 0, ignores the FPC DFP mode and M4 methods,
  keeps the source quantum in FIxTR, abends on M4 8-15, nonzero FIDTR M3 or QADTR M4, the
  tiny-quotient edge and IEDTR specials, treats infinities and NaNs as numbers, misclassifies
  TDCDT and TDGDT, and takes no IEEE or quantum trap. The z390 test pins each
  (red-dragon-6uyp.74).

**DFP conversions (red-dragon-6uyp.56).** CDFTR, CDGTR, CDGTRA, CDLFTR, CDLGTR, CXFTR, CXGTR,
CXGTRA, CXLFTR, CXLGTR, CFDTR, CFXTR, CGDTR, CGDTRA, CGXTR, CGXTRA, CLFDTR, CLFXTR, CLGDTR,
CLGXTR, LDETR, LDXTR, LEDTR, LXDTR, CDSTR, CXSTR, CDUTR, CXUTR, CSDTR, CSXTR, CUDTR, CUXTR, CDPT, CXPT, CDZT, CXZT, CPDT, CPXT, CZDT, CZXT.
Rulings R43, R45, R48, R52.

- To and from fixed and logical call `dfp_builtins()` builtins over `zarch_float`'s
  `dfp_from_integer` and `dfp_to_integer`, through the BFP trap ladder.
- From fixed: M3 0 or 2 (and CDGTR, CXGTR) take the FPC DFP mode; M3 0 or 8-15 suppress the
  quantum exception; M4 bit 1 (X'4') suppresses inexact. Exact results have quantum 1. Only
  CDGTR(A) and CDLGTR can round.
- To fixed (figures 20-18, 20-19): out of range or a NaN is invalid without inexact: masked,
  the nearest end of the range (0 for a NaN to logical, the minimum for a NaN to fixed) and CC
  3; unmasked, `S0C7` DXC 80 with the GR and CC unchanged. Otherwise the CC is the source's
  sign, 0 for a zero.
- LDETR and LXDTR are IR: the biased exponent moves by the bias difference. M4 bit 0 (X'8') is
  XiC: off, an SNaN signals invalid and becomes a QNaN and an infinity loses its digits; on,
  both keep their digits and nothing signals.
- LEDTR and LDXTR call the `load_rounded` builtin, the XiC bit its third argument. The short or
  long result lands in the left of R1, the rest unchanged; a trapped overflow or underflow
  stores the scaled value in the source format (`rounded_stored`, shared with BFP).
- The signed and unsigned packed forms are IR (R52a). CDSTR/CXSTR read 15 or 31 digits and a
  sign nibble from GR R2 or the even-odd pair, CDUTR/CXUTR 16 or 32 digits; a digit above 9 or
  a sign below A is a data exception, DXC 0 in the FPC, `S0C7`, suppressed. The result has
  quantum 1. CSDTR/CSXTR store the rightmost 15 or 31 digits and a sign (D minus, C plus, F
  plus when M4 bit 3), CUDTR/CUXTR 16 or 32 digits; specials convert their trailing digits.
  An odd GR pair register is `S0C6`.
- CDPT/CXPT and CDZT/CXZT read L2 bytes (at most 9/18 and 16/34, else `S0C6`). M3 bit 0 (S)
  makes the rightmost nibble (packed) or zone (zoned) a sign; packed M3 bit 3 (I) ignores it.
  Zones are otherwise ignored. Packed digits beyond 16 or 34 must be zero. Any bad digit or sign
  is DXC 0, `S0C7`, suppressed.
- CPDT/CPXT and CZDT/CZXT store the rightmost L2 bytes of digits: zones F, or 3 with Z (M3
  bit 1); S puts a sign in the rightmost nibble or zone, P (bit 2) makes plus F, F (bit 3)
  makes a zero result plus. Specials convert their trailing digits. CC 0 zero, 1 minus,
  2 plus, 3 special or lost nonzero digits; lost digits then abend `S0CA` after the store
  when the program mask's decimal-overflow bit is on.
- Digits move through `decimal_lanes.py`: an integer spread one digit per four- or
  eight-bit lane, and lanes combined pairwise into the integer, both IR functions defined once
  per program; a lane digit above 9 is found by bit tests on all lanes at once.

**PFPO (red-dragon-6uyp.56, ruling R52d).** PERFORM FLOATING-POINT OPERATION, PoO 9-35 to 9-46.

- GR0 bits 32-63 are decoded in IR. The function is valid when the operation type is 01, both
  format codes are in figure 9-25, their radixes differ, the method is 0, 1 or 8-15, and a BFP
  target has bits 58-59 zero. The test bit sets CC 0 or 3 and a zero return code; otherwise an
  invalid function is `S0C6`.
- Four IR functions, defined once per program (ruling R51), keep the statement small (211
  instructions): `__hlasm_pfpo_valid` checks the word, `__hlasm_pfpo_method` resolves the method
  against the FPC, and `pfpo_codec.py`'s `__hlasm_pfpo_decode` and `__hlasm_pfpo_encode` hold the
  format dispatches: the FPR 4/6 image to the family's field list (BFP and HFP field IR, the DPD
  decoder) and the delivered value merged into the FPR 0/2 image. `pfpo_builtins()` has one
  builtin, `__hlasm_pfpo(word, method, fields)`, over `zarch_float.convert_radix`; method 0 and
  1 are the FPC DFP and BFP modes.
- GR1 bits 32-63 take 0, or the scaling exponent when a trapped overflow or underflow delivers
  the scaled value (1 <= |z| < radix). With bit 57 (alternate action) that trap sets the DXC
  and CC 2 and does not interrupt. PFPO runs the shared BFP ladder, giving it a `LadderEnd`
  (`ladder_end.py`) for the alternate action and the CC 1 that follows a completion without an
  interruption. Invalid suppresses with GR1 unchanged. CC 1 marks a nontrap
  exception.
- Bit 56 suppresses inexact. For a DFP target bit 58 permits the quantum exception and bit 59
  picks the exact result's quantum: 1 when on, the largest when off (figure 9-29). For an HFP
  target bit 58 reports overflow as IEEE overflow (else invalid, +-Hmax) and bit 59 reports
  underflow (else a true zero, inexact). An IEEE NaN becomes +Hmax, an infinity +-Hmax.
- z390 does not emulate CDZT, CXZT, CPDT, CPXT or CZDT, abends on several valid fixed-point
  and LDETR forms, ignores M3 methods and the PFPO controls, return code and CC 1, and takes no
  DFP IEEE or quantum trap. The z390 test pins each to the PoO (red-dragon-6uyp.74).

**Vector registers (red-dragon-6uyp.90).** The layout wave 2 builds on (`docs/superpowers/specs/2026-10-23-hlasm-vector-design.md`, ruling R53).

- `__hlasm_vrs` holds 32 vector registers of 16 bytes, VR v at offset 16v, big-endian. FPR f is
  bytes 0-7 of VR f. Scalar FP writes and pair reads leave bytes 8-15 unchanged, one of the
  outcomes PoO 2-6 permits.
- A whole VR is one unsigned 128-bit value (`load_vr`, `store_vr`). Element i of size s is
  bytes i*s to i*s+s-1. A static index at or past the element count abends `S0C6` at
  lowering; a run-time index is taken modulo the count, as z15 does (PoO leaves it
  unpredictable).
- Element functions return one value: the result in bits 0-127, CC at 128-129, FPC flags at
  136-143, VXC at 144-151 and a trap bit at 152. The caller splits it with shifts and masks.
- An omitted trailing M operand is 0. An element size outside the instruction's allowed set,
  or a set must-be-zero M bit, abends `S0C6` at lowering (R34).
- A VRV operand D2(V2,B2) arrives as a storage operand whose index is a VR. It is read as its
  own type, so the GPR address path cannot take it; the address adds V2's element.
- A vector-processing exception (PIC 001B) stores the VXC (index << 4 | code) in FPC byte 2
  and abends `S0DB`, as PIC 0013 gives `S0D3` and 001D `S0DD`.
- Our che4z fork exports `VZERO v` as `VGBM v,0`. Upstream che4z gives `VGBM 1,v`.
- Our fork exports `VACQ` and `VACCCQ` with V4 in place and M5 4 after it. Upstream inserts 4
  before V4, so register 4 replaces V4 and V4 becomes the mask.

**Vector loads and stores (red-dragon-6uyp.57.1).** VL, VLR, VLM, VST, VSTM, VLL, VSTL, VLBB,
VLREP, VLEB/H/F/G, VLEIB/H/F/G, VLLEZ, VSTEB/H/F/G, VGEF, VGEG, VSCEF, VSCEG, VLBR, VLBRREP,
VLEBRH/F/G, VLLEBRZ, VLER, VSTBR, VSTEBRH/F/G and VSTER (PoO chapter 21). che4z exports every
extended mnemonic (VLREPB, VLLEZLF, VLBRQ, LDRV, LERV, STERV, STDRV, VSTERG, ...) as its base
with the implied M3. No builtin: every form is region copies, shifts and masks.

- Alignment hints (M3 of VL and VST, M4 of VLM and VSTM) are ignored.
- VLM and VSTM move V1 to V3 as one region copy. They do not wrap: V3 below V1, or more than
  16 registers, abends `S0C6` (PoO 21-14, 21-26). The unit's plan said they wrap from 31 to 0;
  that was wrong.
- Element forms touch only their element's bytes. The M3 index must be below the element
  count; VLEI sign-extends I2 to the element. VLREP and VLBRREP replicate one element by a
  multiply. VLLEZ and VLLEBRZ put the element in the rightmost element of the left doubleword,
  or bytes 0-3 for M3 6, and zero the rest.
- VLL and VSTL move min(R3 bits 32-63, 15) + 1 bytes, one byte at a time; VLL zeroes V1 first.
  VLBB loads up to the boundary of a 64 << M3 byte block (M3 0-6), at most 16 bytes, and zeroes
  the bytes past it. The PoO leaves those bytes unpredictable, so tests do not assert them; a
  unit test pins the block arithmetic instead.
- VGEF, VGEG, VSCEF and VSCEG add element M3 of V2 to D2(B2) through the VRV operand, and read
  it before V1 is written, so V1 may equal V2.
- VLBR and VSTBR reverse the bytes of each element (ES H, F, G, Q); VLER and VSTER reverse the
  element order (ES H, F, G).
- Every invalid M field, index or range abends `S0C6` at lowering, before any access.

**Vector register manipulation (red-dragon-6uyp.57.2).** VGBM, VGM, VGEM, VLGV, VLVG, VLVGP,
VMRH, VMRL, VPDI, VPERM, VBPERM, VPK, VPKS, VPKLS, VREP, VREPI, VSEG, VSEL, VBLEND, VUPH, VUPL,
VUPLH and VUPLL (PoO chapter 21), with every extended mnemonic (VZERO, VONE, VGMB, VPKSHS,
VUPLHW, VBLENDQ, ...), which che4z exports as its base with the implied masks. No builtin.

- Each form reads its source VRs whole and writes V1 whole, so V1 may name any source, except
  VREP (reads one element of V3), VLGV (reads one element) and VLVG (writes one element).
- VMRH, VMRL, VPK, VPDI, VUPLH and VUPLL gather bytes of V2 || V3 (or V2) by a static map.
  VUPH and VUPL then fill each element's high half from the sign bit; VSEG does the same per
  doubleword.
- VGBM and VGM are constants. VGM takes I2 and I3 modulo the element's bits and wraps when I2
  is past I3. VREP checks its index at lowering; VREPI sign-extends I2 to the element.
- VPERM picks each byte of V2 || V3 by the low five bits of V4's byte. VBPERM picks bits of V2
  followed by 128 zeros into bits 48-63 and zeroes the rest. VSEL selects bitwise; VBLEND by
  bit 0 of each V4 element. Neither works over a concatenation.
- VLGV and VLVG index the element by the D2(B2) address modulo the element count, which is the
  low 12 bits modulo the count. Past the count the PoO leaves the result unpredictable; tests
  pin the modulo in the IR, not the value.
- VPKS and VPKLS call one element function per signedness and element size. It returns the
  packed result and the CC (0 none saturated, 1 some, 3 all) in the element return
  convention; the CC is set only when M5's CS bit is on.
- An element size outside the PoO's set, or a VREP index past the count, abends `S0C6` at
  lowering. A negative static index is its field's unsigned image (VREP -1 is X'FFFF'), so it
  abends too (R108).

**Vector integer logical, compare and counts (red-dragon-6uyp.57.3).** VN, VNC, VNN, VNO, VNX,
VO, VOC, VX, VEVAL, VCEQ, VCH, VCHL, VEC, VECL, VMN, VMNL, VMX, VMXL, VTM, VLC, VLP, VPOPCT,
VCLZ and VCTZ (PoO chapter 22), with every extended mnemonic (VNOT, VCEQBS, VCHLQ, VECLG,
VPOPCTB, ...), which che4z exports as its base with the implied masks. No builtin.

- Each form reads its source VRs whole and writes V1 whole, so V1 may name any source.
- The bitwise forms and VEVAL work on whole registers. VEVAL ORs one minterm of V2, V3 and V4
  per one bit of I5; bit 0 of I5 is the index A B C = 000.
- VMN, VMNL, VMX, VMXL, VLC and VLP unroll one piece per element. Signed order is unsigned order
  with each sign bit flipped. VLC and VLP leave the most negative element as it is, with no
  exception (PoO 22-17).
- VCEQ, VCH and VCHL call one element function per operation and element size. It returns the
  element masks and the CC (0 all true, 1 some, 3 none); the CC is set only when M5's CS bit is
  on.
- VEC and VECL compare byte 7, halfword 3, word 1, doubleword 0 or quadword 0 of V1 and V2 (PoO
  Figure 22-2), and VTM tests V1 under the V2 mask. They set only the CC.
- VPOPCT sums bits over the whole register, then folds byte counts into each element. VCLZ and
  VCTZ smear the leading or trailing one across the rest of its element and subtract the
  population count from the element's bits.
- ES 4 is allowed everywhere except VPOPCT (ES 0-3). An element size outside the PoO's set
  abends `S0C6` at lowering.

**Vector integer arithmetic (red-dragon-6uyp.57.4).** VA, VAC, VACC, VACCC, VS, VSBCBI, VSBI,
VSCBI, VAVG, VAVGL, VD, VDL, VR, VRL, VMAE, VMAH, VMAL, VMALE, VMALH, VMALO, VMAO, VME, VMH, VML,
VMLE, VMLH, VMLO, VMO, VMSL, VGFM, VGFMA, VCKSM, VSUM, VSUMG and VSUMQ (PoO chapter 22), with
every extended mnemonic (VAQ, VACQ, VMLHW, VMALHW, VDF, VMSLG, VSUMQF, ...). No builtin.

- Each form reads its source VRs whole and writes V1 whole, so V1 may name any source.
- Element-wise forms unroll one piece per element; masking each piece to its element on
  assembly gives the wraparound. A signed element is the unsigned one minus 2^bits when its
  sign bit is on. The signed average flips each sign bit, averages unsigned and flips back.
- VAC, VACCC, VSBI and VSBCBI are 128-bit; only bit 127 of V4 is the carry or borrow, and M5
  must be 4.
- The even, odd, multiply-and-add-even/odd, Galois-field and VMSL forms produce double-wide
  elements from the even and odd elements of V2 and V3 and the double-wide element of V4.
  Carry-less multiply XORs the multiplicand shifted by each one bit of the multiplier. VMSL's M6
  bit 0 shifts the even product left one bit and bit 1 the odd one.
- VCKSM adds the four words of V2 to word 1 of V3, adding each carry back into bit 31, into
  word 1; the other words are zero. VSUM, VSUMG and VSUMQ add the sub-elements of each word,
  doubleword or quadword of V2 and the rightmost one of V3's.
- VD, VDL, VR and VRL (ES 2-4) call one element function per operation, element size and IDC.
  Quotients truncate toward zero and remainders take the dividend's sign. A zero divisor, or
  VD's negative maximum by -1, is an integer-divide condition. Without M5's IDC bit the function
  returns the trap bit and the VXC (lowest faulting index, VIC 8); the caller stores the VXC in
  the FPC and abends `S0DB` before V1 is written. With IDC that element's result is zero.
- An element size outside the PoO's set abends `S0C6` at lowering. Reserved "should be zero" M
  bits (VD/VR M5 bits 1-3, VMSL M6 bits 2-3) are ignored.

## Known Gaps

- Only SVC and the load and store, load address and immediates, signed add and subtract, logical add and subtract, compare, compare and branch or trap, boolean, shift and rotate, multiply and divide, load and test with the sign changes, test under mask, storage move, storage compare, translate, branch on condition, branch and link, branch on count and index, execute, conditional load and store, select and bit count, interlocked-update, Unicode conversion and string search, high-word, miscellaneous, packed-decimal arithmetic, packed-decimal compare and test, decimal conversion, edit, floating-point-support, BFP arithmetic, BFP conversion, HFP arithmetic, HFP conversion and DFP arithmetic units, DFP conversion and PFPO, and the vector loads, stores, register manipulations, integer logical, compare and count instructions and integer arithmetic, are lowered; the rest are tracked as opcode-unit beads under red-dragon-6uyp.
- Floating-point arithmetic is the leaf `zarch_float` ([zarch-float.md](zarch-float.md)); `bfp_builtins.py`, `hfp_builtins.py`, `dfp_builtins.py` and `pfpo_builtins.py` reach it (red-dragon-6uyp.51, .53 to .56).
- QY raises `UnsupportedDataType` (its 20-bit long-displacement image, red-dragon-6uyp.103), as do G and R (red-dragon-6uyp.63). Our che4z fork takes EB/DB/LB lengths down to 9/12/16 bits and a ±2^31 exponent modifier with a type extension, as the Language Reference allows. It still refuses a scale modifier on EB/DB/LB (the manual ignores it with a warning) and caps the E/D/L scale at 5/13/27 (Table 33; the scale-modifier section says 14/14/28). A bit-length A-constant whose values name `*` raises it too: che4z steps each copy's `*` by the bit length as if it were bytes, and the Language Reference does not say how `*` advances inside a byte (red-dragon-6uyp.97).
- SY is halfword aligned (the Language Reference's S-type table); z390 does not align it, so the z390 differential places SY on an even offset. z390 also rejects F and H fractions without a scale modifier, rounds FS1'0.25' to 0, wraps out-of-range values and steps `*` across a literal's copies; those cases follow the Language Reference and are unit tests. z390 also misplaces several bit-length forms (duplicated or followed by a byte operand, X, Z), and misassembles floating-point constants: it rejects rounding suffixes, (INF), the NaNs and (DMIN), keeps an unextended zero's sign, ignores scale digits, applies EE2 as E-2, sets (MIN) wrong, truncates where a length modifier rounds, overflows BFP values just under Nmax and DFP values it should fold, and drops a DFP zero's quantum. The VM test for these forms cites the Language Reference; a z390 test pins z390's images (red-dragon-6uyp.74). AMODE/RMODE are not read.
- Falling through into DC/DS data or past a CSECT's end skips the data instead of executing it, and a branch into data abends `S0C1` (red-dragon-6uyp.64).
- Every branch, even to a static relative target, walks the dispatch chain (red-dragon-6uyp.80).
- Compile time is linear in IR size but about 0.17 ms per IR instruction, nearly all in the linker
  and the unit codec (red-dragon-fu6c). EX of a register-field target (RR, RX, RS, RI, RIL and
  the like) still expands up to 256 copies.
- A J-constant naming a class, a control section or a DSECT no Q-constant names is refused by the binder (`UnsupportedBinding`, red-dragon-6uyp.104).
  An LTR on an unresolved EXTRN sees its stub address, not 0 (ruling R66).
- LOAD returns the same copy every time: there is no fresh copy for a non-reusable module.
  LINK and LOAD find only SD and LD names of the image. A LINK to a missing name raises, as a
  COBOL dynamic CALL does, even when unresolved targets are permitted; its PARAM list is not
  passed. z390's LINK returns R15 as 0; its test pins that (red-dragon-6uyp.74).
- The layout of LOAD's ERRET code in R1 is unconfirmed: IBM's LOAD page says only "system
  completion code", and we use the ABEND macro's bits 8-19 (`X'00806000'`), not `X'00000806'`.
- Machine-instruction bytes are not in section storage (a spec non-goal: self-modifying code), so `CLC` against code does not see them. EX finds its target at assembly instead.
- An EX target written with an explicit base or an index, an EXRL to an absolute target, or one
  where no machine statement starts abends `S0C1` with a logged warning (red-dragon-6uyp.77). EX
  ignores the base register's run-time value.
- EX and EXRL do not model R1 bits ORed into opcode bits; che4z exports no opcodes. Any R1 bit in
  an opcode position abends `S0C1`, even one the opcode already has; byte-1 shapes not in the
  table (SS-d, the vector formats) count as opcode (red-dragon-6uyp.78).
- che4z encodes LHHR and LLHFR without the Z bit, where the Principles of Operation (Figure 7-397) define RISBHGZ and RISBLGZ; the range is the whole word, so the result is the same.
- AMODE 24 and 64 are not modelled: SAM24, SAM64 and BASSM or BSM into those modes
  abend `S0C1` (red-dragon-6uyp.75). A BASSM or BSM to the return address returns
  whatever mode it selects.
- GETMAIN, FREEMAIN and STORAGE never reuse freed storage, never fail, ignore `LOC`, and
  do not model subpool semantics beyond matching a release to its request. Only the R,
  RU and RC forms are lowered. A subpool FREEMAIN (SVC 10 with R1 = 0) abends `SA0A`
  instead of freeing the subpool. TIME supports `DEC` and `BIN` with `LINKAGE=SVC`.
- Access registers hold values only; no instruction addresses through them. LAE and LAEY do
  not set access register R1 (red-dragon-6uyp.86).
- `run()` adds the HLASM run inputs its caller does not supply (`unsupplied_run_input_builtins()`:
  the host clock, an empty PARM and no DD definitions). Callers add the rest through `run()`'s
  `builtins` and `io_provider`:
  - the floating-point builtins `bfp_builtins()`, `hfp_builtins()`, `dfp_builtins()` and
    `pfpo_builtins()`, which are not run inputs; the `interpreter.py` CLI adds them. Without them a
    floating-point instruction stores what the unresolved-call strategy gives;
  - `declare_file_builtins()`, for OPEN;
  - a PARM, from `run_input_builtins(clock, parm)`;
  - the DDs, from `dd_run_inputs(dds)`: its `__hlasm_dd` builtin, and its `RunInputs` given to the
    file provider. That is where each DD's path goes: OPEN of a DDNAME reads and writes that path;
  - the file provider, `RealFileProvider(inputs)` from `interpreter.record_io`, as `io_provider`.
    It opens a file only at the path a DD gives; a DDNAME with no DD fails the open.

  Every part exists in this repository and none imports `interpreter.cobol`. red-dragon-forge
  composes them, with COBOL's, into the run-time stack (red-dragon-6lic).
- DCBD maps `DCBMACR` at 50, as before OPEN. `DCBMACRF` (offset 42 after OPEN) is not mapped:
  DDNAME stays at 40, so nothing is moved there.
- GET on a DCB opened OUTPUT or EXTEND branches to EODAD rather than failing; CLOSE always sets
  R15 to 0, and an OPEN of a DCB already open re-opens it with R15 0 (ruling R87; IBM's codes for
  these are unconfirmed).
- QSAM only, sequential, RECFM F, FB, V and VB: BSAM, VSAM and EXCP, DCBE, exit lists, SYNAD
  (so a wrong-length fixed record, such as a short last record, is returned as a record),
  UPDAT and the other OPEN modes, `MODE=31` lists and the BLKSIZE of a file (VB files are read
  and written with RDWs and no block descriptors) are out of scope.
- A hand-coded `L 15,48(,1)` and `BALR 14,15` into a DCB's GET routine is not supported: the
  DCB holds no routine address.
- A branch to a label that lies in CNOP alignment padding abends `S0C1` (red-dragon-6uyp.102); OPEN
  and CLOSE label the instruction after their CNOP.
- The file provider is the COBOL one and finds files by name, so a COBOL file and an HLASM
  DDNAME share one namespace in a mixed image.
- DCB checks an `EODAD` or `SYNAD` against 2^24 only when it is a self-defining term; a
  relocatable one is not checked, since sections are placed far below 16 MB.
- In AMODE 31, LM, STM, LMD, NC, OC, XC, the decimal instructions and the storage moves, compares and translates do not wrap
  EA + offset at 2 GiB; MVCL's overlap test ignores operands that wrap.
- SRST and SRSTU with R1 below R2 search past the top of storage instead of wrapping to 0.
- MVCLE, MVCLU, MVST, CLCLE, CLCLU, CLST, CUSE, TRE, TROO, TROT, TRTO, TRTT, TRTE, TRTRE,
  SRST, SRSTU and the Unicode conversions finish in one execution, since the CPU-determined amount may be the whole operand: they never
  set CC 3 (ruling R28). MVCLU abends `S0C6` on an odd length, which the
  Principles of Operation leave to the model.
- ICM and CLM with mask 0 raise no access exception for their operand.
- Addresses differ from z390's load point.
- One CPU (ruling R33): interlocked updates, serialization and what other CPUs or channel programs
  observe hold trivially; no lock is modelled. LPD and LPDG always set CC 0.
- Each PLO statement lowers its whole function-code table inline, about 7,300 IR instructions; the
  50 codes that do not use R1 or R3 could be emitted once per program (red-dragon-6uyp.83). Lowering
  logs a warning per PLO statement with its IR count.
- COBOL linkage, where IBM's COBOL manuals are silent (our rulings; R83 and
  `docs/superpowers/plans/2026-10-24-hlasm-unit-cobol-linkage.md`): 1- and 2-byte BY VALUE
  values widen to a word by their signedness, a signed item sign-extended (S9(4) -2 gives
  X'FFFFFFFE') and an unsigned one zero-extended, as LE ILC widens C char and short; an 8-byte
  value takes two words; no VL bit follows a trailing BY VALUE. A BY VALUE length other than 1, 2, 4 or 8, which IBM
  refuses, gives a zero word (COBOL → HLASM) or a zero-filled copy (HLASM → COBOL).
  RETURN-CODE is a halfword: COBOL keeps R15's low halfword.
- LINK and LOAD do not find COBOL programs of a mixed image (red-dragon-6uyp.100).
- `ABEND` takes only a self-defining code of 0-4095. Register notation (`ABEND (R2)`) and larger codes are not supported.

## Test Coverage

| Test file | Covers |
|---|---|
| `tests/unit/hlasm/lowering_helpers.py` | Operand and statement builders and the IR describer the lowering unit tests share |
| `tests/unit/hlasm/storage_events.py` | A lowering's storage reads and writes, abends and CC stores in order, for the decimal lowering tests |
| `tests/unit/hlasm/test_program_model.py` | Bridge JSON models |
| `tests/unit/hlasm/test_bridge_exit_codes.py` | Parser exit-code handling |
| `tests/unit/hlasm/test_operands.py` | Typed operand access and its failures |
| `tests/unit/hlasm/test_machine.py` | Machine start-up state, the empty allocation table |
| `tests/unit/hlasm/test_vector_registers.py` | Vector registers on the VM: 128-bit values over the FPRs, elements by static and run-time index, return fields, M-field checks, the VRV address, the VXC |
| `tests/unit/hlasm/test_vector_memory_lowering.py` | Vector load and store IR: 16 bytes per register in one copy, one element's bytes for element forms, byte loops after zeroing for VLL and VLBB, VLBB's block mask and size from M3, V2 read first for VRV, `S0C6` before any access, no SYMBOLIC in all 38 |
| `tests/unit/hlasm/test_vector_logical_compare_lowering.py` | Vector logical and compare IR: sources read whole and V1 written whole, VEC/VECL reading the PoO's element and VTM setting only the CC, one compare function per operation and size with the CC set only for CS, `S0C6` before any access, no SYMBOLIC in all 24 |
| `tests/unit/hlasm/test_vector_integer_arithmetic_lowering.py` | Vector integer arithmetic IR: sources read whole and V1 written whole, one divide function per operation, size and IDC with the `S0DB` exit only without IDC, `S0C6` before any access, no SYMBOLIC in all 35 |
| `tests/unit/hlasm/test_vector_register_lowering.py` | Vector register-manipulation IR: sources read whole and V1 written whole, VLGV and VLVG index modulo the element count, one pack function per kind and size with the CC set only for CS, `S0C6` before any access, no SYMBOLIC in all 23 |
| `tests/unit/hlasm/test_assembly_diagnostics.py` | Bridge diagnostics and DC warnings as unit diagnostics: severity, code and text, member names, call stack, once per value, literals, DSECTs and duplication 0 checked, the macro named |
| `tests/unit/hlasm/test_dc_encoding.py` | DC images |
| `tests/unit/hlasm/test_floating_point_constant.py` | E, D and L images: HFP without extension and with H, BFP and DFP rounding modes and lengths, special values, and the ASMA071E, ASMA064S and ASMA073E refusals |
| `tests/unit/hlasm/test_fixed_width_ir.py` | Fixed-width arithmetic, truncating division, bitwise connectives, shifts and rotates, and condition codes |
| `tests/unit/hlasm/test_hlasm_emitter.py` | The chain shares what it extends; the emitter's order and per-statement source locations |
| `tests/unit/hlasm/test_lowering_skeleton.py` | Labels, LR, BASR, BALR, BRAS and BCR, dispatch, abends |
| `tests/unit/hlasm/test_load_store_lowering.py` | Load and store IR: GPR and storage accesses, alignment branch, CC, no SYMBOLIC |
| `tests/integration/hlasm/test_load_store.py` | Every load and store mnemonic on the VM: registers, run status and CC; alignment abends |
| `tests/unit/hlasm/test_load_address_immediate_lowering.py` | Load address and immediate IR: GPR widths read and written, index sum shifted before the base is added, no CC |
| `tests/integration/hlasm/test_load_address_immediate.py` | Every load address and immediate mnemonic on the VM, CC unchanged |
| `tests/unit/hlasm/test_signed_add_subtract_lowering.py` | Signed add and subtract IR: operand widths, CC, the `S0C8` trap and its program-mask condition |
| `tests/integration/hlasm/test_signed_add_subtract.py` | Every signed add and subtract mnemonic on the VM: result, CC 0-3 |
| `tests/unit/hlasm/test_logical_add_subtract_lowering.py` | Logical add and subtract IR: operand widths, carry-in read, CC, no trap |
| `tests/integration/hlasm/test_logical_add_subtract.py` | Every logical add and subtract mnemonic on the VM: result, CC with carry and borrow |
| `tests/unit/hlasm/test_compare_lowering.py` | Compare IR: operand widths read, nothing written, only the CC set, relative-long alignment |
| `tests/integration/hlasm/test_compare.py` | Every compare mnemonic on the VM: CC, operands unchanged, alignment abends |
| `tests/unit/hlasm/test_compare_branch_trap_lowering.py` | Compare-and-branch and trap IR: the M3 bit tested on the unstored comparison, branch or `S0C7`, masks 0 and 14, load written before the zero test |
| `tests/integration/hlasm/test_compare_branch_trap.py` | Every compare-and-branch, compare-and-trap and load-and-trap mnemonic and a spread of extended ones on the VM: path, trap, loaded register, CC unchanged, immediate widths, masks 0, 1, 14 and 15 |
| `tests/integration/hlasm/test_data_exception_code.py` | Each non-IEEE data exception on the VM stores its DXC in FPC byte 2 and keeps the rest: 00 for a decimal operand, FF for compare-and-trap and load-and-trap |
| `tests/unit/hlasm/test_boolean_lowering.py` | Boolean IR: operand widths, the field read and replaced, the CC; NC/OC/XC as one byte loop of fixed size |
| `tests/integration/hlasm/test_boolean.py` | Every boolean mnemonic, NOTR and NOTGR on the VM: result, CC 0 and 1, field CCs, overlapping storage operands, implicit and explicit-0 lengths, `__hlasm_ss_any` reset between statements |
| `tests/unit/hlasm/test_shift_rotate_lowering.py` | Shift and rotate IR: registers only, CC only for the signed and selected-bits forms, the `S0C8` trap, an odd pair abends `S0C6`, register-span masks |
| `tests/integration/hlasm/test_shift_rotate.py` | Every shift and rotate mnemonic and every RISBG-family extended mnemonic on the VM: result, CC 0-3 or unchanged, amounts 33 and 65 |
| `tests/unit/hlasm/test_load_sign_lowering.py` | Load and test, complement, positive and negative IR: operand widths, the `S0C8` trap only for LCR, LCGR, LPR, LPGR and only with the mask bit on |
| `tests/integration/hlasm/test_load_sign.py` | Every load and test, complement, positive and negative mnemonic on the VM, the maximum negative number included |
| `tests/unit/hlasm/test_test_under_mask_lowering.py` | Test under mask IR: the byte or register read, the halfword shift, nothing written, only the CC set |
| `tests/integration/hlasm/test_test_under_mask.py` | Every test under mask mnemonic on the VM: CC 0-3 for every halfword, TMY with a negative and a beyond-4095 displacement, registers and storage unchanged |
| `tests/unit/hlasm/test_multiply_divide_lowering.py` | Multiply and divide IR: operand widths, CC and the `S0C8` trap only for the checked forms, the two `S0C9` checks before the pair is written, an odd pair abends `S0C6` |
| `tests/integration/hlasm/test_multiply_divide.py` | Every multiply and divide mnemonic on the VM: products, quotients, remainders, CC; zero divisors and oversized quotients abend `S0C9` with the registers kept |
| `tests/integration/hlasm/test_shift_rotate_mnemonics.py` | RISBG-family extended spellings reach their base mnemonic and immediates through the bridge |
| `tests/unit/hlasm/test_branch_on_condition_lowering.py` | Branch on condition IR: the CC mask test, each form's target, the forms that lower to nothing |
| `tests/integration/hlasm/test_branch_extended_mnemonics.py` | Every branch on condition, compare-and-branch and compare-and-trap extended spelling reaches its base mnemonic and mask through the bridge; JCT, JCTG, the JX spellings, JAS and JASL reach theirs with R1 |
| `tests/integration/hlasm/test_branch_on_condition.py` | Every branch on condition mnemonic and a spread of extended mnemonics on the VM: path taken, CC unchanged, branches into data abend `S0C1` |
| `tests/unit/hlasm/test_branch_and_link_lowering.py` | Branch and link IR: target read before the link is written, the AMODE 31 link word, the BASSM and BSM mode test, SAM and TAM |
| `tests/integration/hlasm/test_branch_and_link.py` | Every branch and link mnemonic, JAS and JASL on the VM: link relative to the next instruction, path, CC; BSM 0,14 and BASSM 14,14 return to the caller; SAM24, SAM64 and switches into AMODE 24 or 64 abend `S0C1`, entering those modes xfailed (red-dragon-6uyp.75) |
| `tests/unit/hlasm/test_loop_branch_lowering.py` | Branch on count and index IR: target first, operands read before R1 is written, wrap, nonzero or signed test |
| `tests/integration/hlasm/test_loop_branch.py` | Every branch on count and index mnemonic, JCT, JCTG and the JX spellings on the VM: counting loops, register overlaps, signed wrap, CC unchanged |
| `tests/unit/hlasm/test_ss_move_lowering.py` | Storage move IR: immediate store widths, the MVC block move beside its byte loop, the nibble loops, odd long-move registers abend `S0C6` |
| `tests/integration/hlasm/test_ss_move.py` | Every storage move mnemonic on the VM: storage, registers, CC; MVC, MVN, MVZ, MVCIN and MVO overlap, MVCRL's hole, MVO truncation, MVCL CC 0-3, zero first lengths and pad, MVCLE and MVCLU pads; MVCLU odd length and MVST's GR0 abend `S0C6`; the bridge passes MVO lengths as written |
| `tests/unit/hlasm/test_ss_compare_lowering.py` | Storage compare IR: CLC's one block read per operand, an equality test then an order, one unit of each operand per loop iteration, no comparison on a byte image, no storage writes, odd pair registers abend `S0C6` |
| `tests/integration/hlasm/test_ss_compare.py` | Every storage compare mnemonic on the VM: CC 0-2 and registers; CLC lengths 0 and 256, inequality against the pad, zero lengths, bit 32 cleared or kept, a pad from a base register, CLST ending first and a high ending character, CUSE found, ended, zero substring and negative lengths; CLCLU odd length and CLST's GR0 abend `S0C6` |
| `tests/unit/hlasm/test_translate_lowering.py` | Translate IR: one unit and one function per iteration at each form's widths, stores only where the form translates, no comparison on a byte image, M3 bit 3 drops the test, odd pairs abend `S0C6` |
| `tests/integration/hlasm/test_translate.py` | Every translate mnemonic on the VM: storage, registers, CC; TR overlap and lengths, TRT and TRTR CC 0-2 and bit 32, TRE found, ended and length 0, the test character and its control, ignored table bits, each TRTE and TRTRE control; odd lengths abend `S0C6` |
| `tests/unit/hlasm/test_execute_lowering.py` | Execute IR: byte 1 decoded per format, R1 = 0 or an unlowered target lowers one copy at the EX, a register field one copy per reachable value under a tree, a data field (MVC, CLI, SVC) one lowering with byte 1 from R1 and one-byte region accesses, the opcode-bit guard, `S0C3` and `S0C6` before any copy, unresolved targets abend `S0C1` with a warning |
| `tests/integration/hlasm/test_execute.py` | EX and EXRL on the VM: MVC length codes 0, 4, 7 and 255 and a destructive MVC, CLC, NC, OC, XC, TR, TRT, TRTR, MVN, MVZ, MVCIN and MVO lengths, CLI, CLIY, MVI, MVIY, TM, NI, NIY, OI, XI, ASI, AGSI and ALSI immediates (negative ones sign-extended after the OR), an SVC number, BAL, BRAS, AR and LHI fields, a BC mask and index, a branch mask from R1, and EXRL of CIJ with its M3 from R1; links after the execute instruction; CC kept; `S0C3`, `S0C6`; indexed targets and opcode modification xfailed (red-dragon-6uyp.77, red-dragon-6uyp.78) |
| `tests/integration/hlasm/test_bridge_parser.py` | The real bridge: macro origins, refused assemblies; operand placement, modifiers, S-constants, CCW, AMODE/RMODE and diagnostic call stacks |
| `tests/integration/hlasm/test_macro_language.py` | One program per macro-language feature on the VM: printed values and registers |
| `tests/unit/hlasm/test_object_module.py` | ESD, TXT, RLD and END of an assembly with private code, a COM, ENTRY, EXTRN, WXTRN, A and V constants; XD records and the RLDs of Q, QL2, J and CXD; signed items of A(X-Y), Y(X+X-Y+DF), A(X-E1+3) and the image of A(DF+DF) |
| `tests/unit/hlasm/test_binder.py` | Layout offsets, CM merge, name resolution (local, image, COBOL stub, weak zero, stub), entry points, far-branch table, unresolved warning; duplicates in either language; XD merge and pseudo-register layout; a J naming no XD refused |
| `tests/unit/hlasm/test_cobol_linkage.py` | The job step's `__entry_<NAME>` functions, the shared conversion, the far branch's COBOL call |
| `tests/integration/hlasm/test_cobol_linkage.py` | Mixed image: start-up order, entry by name, PROGRAM-ID vs CSECT refused; COBOL → HLASM list with every mode, OMITTED middle and last, RETURN-CODE; HLASM → COBOL by signature, short VL list; nesting with register restore; abend under COBOL; CANCEL |
| `tests/integration/hlasm/test_binder.py` | Two modules: a V-constant to a later module's ENTRY and its data; PARM supplied and empty; BALR to an unresolved EXTRN, permitted and refused; a CSECT in two units refused; two modules sharing DXDs through Q, J and CXD in a GETMAINed area; A(X-Y) and Y(X-Y) across sections and A(E1-E2) across modules |
| `tests/z390/test_binder_differential.py` | The two-module V-constant program against z390's linker (SYSOBJ autolink); A(X-Y), Y(X-Y) and A(E1-E2), which z390's loader refuses (error 119, RC 16, pinned) |
| `tests/integration/hlasm/test_storage_layout.py` | Section regions and address constants; `*` in each constant after `DC 0F`, and in a duplicated literal; out-of-range values refused with their line, a literal's included; CCW images with relocated addresses, a literal operand's included, and an unresolved external address holding its stub; V-constants to another section; an S-type literal resolved through the USING at its pool |
| `tests/integration/hlasm/test_dc_images.py` | DC images loaded into registers on the VM, one family per type group (`dc_image_programs.py`); alignment bytes inside a DC are zero; bit-length and floating-point forms z390 misassembles (`PAST_Z390`) |
| `tests/integration/hlasm/test_svc.py` | `WTO`, `ABEND` user and system codes, unlowered SVCs, `run()` with our maclib then `copybook_dirs`, call-site spans |
| `tests/integration/hlasm/test_hlasm_compile.py` | Unit files; MNOTEs (WARNING and INFO) with their severity and a DC warning logged with place and call stack, and logged again from the cached files with no assembly; reuse that follows the inputs, SYSLIB member contents and the bridge, not the clock; assembly inputs, clock and `&SYSSEQF` printed through WTO; an unsupplied `&SYSPARM` is null and another input not given is refused; a missing SYSLIB directory refused; a bridge name found on `PATH`; the bridge found from another working directory; `run()`, return code, default entry, BALR/BR, wild branch |
| `tests/unit/hlasm/test_bridge_command.py` | The bridge command carries each supplied input and the clock as options; a naive clock and a SYSPARM over 255 characters are refused |
| `tests/integration/hlasm/test_instruction_table.py`, `test_opcode_unit_coverage.py` | Instruction table and opcode-unit coverage |
| `tests/integration/hlasm/test_save_return.py` | `SAVE`, `RETURN`, `YREGS`: registers per range including `(14,15)` and a wrapped range, `T`, `RC`, identifier layout at entry+4 with label and CSECT names, a nested call, operand refusals |
| `tests/z390/test_save_return_differential.py` | The same programs against z390 |
| `tests/integration/hlasm/test_storage_services.py` | `GETMAIN`/`FREEMAIN` R, RU, RC and `STORAGE` with `COND`, `BNDRY=PAGE`, register operands and subpools: two areas aligned, disjoint, written, read and released; `LV=(0)` with the subpool in R0 and `SP=(r)` matched by a literal `SP`; the last byte of a page-aligned area; bad releases abending `SA0A` and `SA78` with the table left as it was; `TIME` DEC and BIN on the fixed clock, by macro and hand-coded `SVC 11` with R1's code, flag bits ignored; operand refusals |
| `tests/z390/test_storage_services_differential.py` | Alignment, disjointness, data and R15 against z390 (z390 sets R15 0 on GETMAIN R and FREEMAIN R); the shape of TIME's words against z390's wall clock; z390 reads a hand-coded SVC 11's format from R0 |
| `tests/integration/hlasm/test_data_set_services.py` | The DCB image at IBM's offsets; every DCBD name read from a DCB; DCB and OPEN operand refusals; a fixed copy in move mode ending at EODAD with R14 after the GET; a locate-mode copy through both buffers; RECFM V with its RDW; `S337` without EODAD or with EODAD 0, `S0C1` for GET or PUT before OPEN, `S013` for an OPEN without LRECL, `S002` for a V PUT over LRECL; OPEN filling empty fields from the DD, failing an unsupplied DD and a hand-built X'81' entry with R15 8 and the DCB untouched, EXTEND appending, and CLOSE skipping a DCB never opened |
| `tests/z390/test_data_set_services_differential.py` | The fixed move, fixed locate and V copies against z390, DDNAMEs through the environment; z390 drops the record a locate PUT leaves at CLOSE |
| `tests/unit/hlasm/test_dd_definitions.py` | `__hlasm_dd` for a DD with every field, one with a path only, and a DDNAME not supplied |
| `tests/unit/hlasm/test_time_service.py` | TIME's words for TOD values across 1900, 2000 (leap day, day 366), 2023 and 2100 |
| `tests/unit/hlasm/test_service_lowering.py` | The program entry prefix matches COBOL's; SVC 6, 8, 9, 10, 11, 19, 20, 120, 200 and 201 call only existing builtins (and LINK the far branch) and leave nothing symbolic |
| `tests/integration/hlasm/test_far_branch.py` | A module entered at its own R14 running there; a call through a V-constant and BALR; a return that skips a level; a branch to the job step's `0xFF0` ending the step; a linking branch into a module below; `B 4(,14)`; a plain branch out that calls; `BSM 0,14` to an R14 without the mode bit; an unowned address abending `S0C1` |
| `tests/z390/test_far_branch_differential.py` | The call and the skipped-level return against z390 (SYSOBJ autolink) |
| `tests/integration/hlasm/test_program_services.py` | CALL inline, `MF=L` and `MF=(E,list)` with VL; LOAD's R0 and R1, `CALL (15)`, DELETE of a loaded name (0), again (4) and of an unloaded one (4); LINK with PARAM and VL leaving the program's registers, by `EPLOC=addr`, `EPLOC=(r)` and a hand-coded R15 list, and a callback inside it branching to `0xFF0`; a missing name: LINK raising in both modes, its lowercase `EP=` name uppercased, LOAD `S806` by macro and by hand with a leftover R15, and ERRET; operand refusals |
| `tests/z390/test_program_services_differential.py` | CALL, LINK and LOAD return codes against z390, z390's LINK R15 pinned; the registers LINK leaves (R7, R9's VL bit) |
| `tests/z390/test_foundation_differential.py` | Return code, WTO, user abend and assembly failure against z390 (`-m z390`) |
| `tests/z390/test_z390_log.py` | Registers and CC from a z390 abend dump (default run) |
| `tests/z390/test_macro_language_differential.py` | The macro-language programs against z390; z390's attribute differences pinned (`-m z390`) |
| `tests/z390/test_load_store_differential.py` | Load and store families, ICM CC, and the alignment difference against z390 (`-m z390`) |
| `tests/z390/test_load_address_immediate_differential.py` | Address and immediate families against z390; the LAE `S0C5` and LXA `S0C1` differences (`-m z390`) |
| `tests/z390/test_signed_add_subtract_differential.py` | Every signed add and subtract mnemonic against z390 (`-m z390`) |
| `tests/z390/test_logical_add_subtract_differential.py` | Every logical add and subtract mnemonic against z390; six z390 CC differences pinned (`-m z390`) |
| `tests/z390/test_boolean_differential.py` | Every boolean mnemonic, NOTR and NOTGR against z390; eleven z390 differences (field CCs, XI, OC overlap) pinned (`-m z390`) |
| `tests/z390/test_shift_rotate_differential.py` | Every shift and rotate case against z390; z390's 32-bit shifts mod 32, RISBGN `S0C1` and refused shift-logical-high spellings pinned (`-m z390`) |
| `tests/z390/test_load_sign_differential.py` | Every load and test, complement, positive and negative case against z390; LTGR's missing R1 write pinned (`-m z390`) |
| `tests/z390/test_multiply_divide_differential.py` | Every multiply and divide case and divide exception against z390; z390's missing quotient-overflow exceptions pinned (`-m z390`) |
| `tests/z390/test_ss_move_differential.py` | Every storage move case and specification exception against z390, bar MVCRL; z390's MVN and MVZ overlap, MVCLU `S0C1` and MVST GR0 differences pinned (`-m z390`) |
| `tests/z390/test_ss_compare_differential.py` | Every storage compare case against z390; z390's CLCL pad, CLCLU, CLST and CUSE differences pinned (`-m z390`) |
| `tests/z390/test_translate_differential.py` | Every translate case against z390; z390's TRE length 0, TROO table alignment and TRTE argument truncation pinned (`-m z390`) |
| `tests/z390/test_test_under_mask_differential.py` | Every test under mask case against z390; no differences (`-m z390`) |
| `tests/z390/test_execute_differential.py` | Every execute case against z390; z390's missing odd-target check, BRAS link and ALSI carry CC pinned, and the targets RedDragon abends on run there (`-m z390`) |
| `tests/z390/test_compare_branch_trap_differential.py` | Every compare-and-branch and trap case against z390; z390's `S0FF` load-and-trap abend and missing CLT and CLGT pinned (`-m z390`) |
| `tests/z390/test_compare_differential.py` | Every compare mnemonic against z390; the relative-long alignment difference pinned (`-m z390`) |
| `tests/z390/test_branch_on_condition_differential.py` | Every branch on condition case against z390; the BIC, BPP and BPRP differences and branches into data pinned (`-m z390`) |
| `tests/z390/test_address_constant_differential.py` | `*` in duplicated and multi-value A-constants against z390 (`-m z390`) |
| `tests/z390/test_dc_image_differential.py` | The DC image families against z390 (`-m z390`). Alignment padding is VM-only: z390's loader fills skipped bytes with X'F6'. z390's images for the floating-point forms it misassembles are pinned |
| `tests/z390/test_branch_and_link_differential.py` | Every branch and link case and the mode-setting returns against z390; z390's AMODE 24 and 64 switches pinned (`-m z390`) |
| `tests/z390/test_loop_branch_differential.py` | Every branch on count and index case against z390; z390's late reads of R2 and the compare value pinned (`-m z390`) |
| `tests/unit/hlasm/test_conditional_select_count_lowering.py` | Conditional, select and count IR: the CC mask tested before any operand, SELECT's reads before its write, FLOGR's odd pair `S0C6`, branch-free counts with no builtin, one loop for BEXTG and BDEPG, the count IR's values |
| `tests/integration/hlasm/test_conditional_select_count.py` | Every conditional, select and count mnemonic and every extended suffix on the VM: met and unmet conditions, masks 0 and 15, kept halves, aliased registers, zero and full operands; CC |
| `tests/integration/hlasm/test_vector_extended_mnemonics.py` | VZERO and VONE reach VGBM of their own register; VACQ and VACCCQ keep V4 and append M5 4 |
| `tests/integration/hlasm/test_vector_memory.py` | Every vector load and store family on the VM, read back with VST and VSTE: VLM/VSTM over 2 and 16 registers, element indexes, VLEI signs, replication, zero extension, VLL/VSTL with R3 0, 6, 15 and above, gather and scatter with V1 = V2, byte and element reversal for H, F, G, Q; invalid fields and VLM/VSTM ranges (V3 below V1, 17 registers) `S0C6` with storage unchanged; VLBB at every block size, only the loaded bytes asserted |
| `tests/integration/hlasm/test_vector_logical_compare.py` | Every vector logical, compare, min/max, complement and count family on the VM, read back with VSTM and IPM, with V1 equal to a source: bitwise forms, VEVAL with an asymmetric function, VCEQ/VCH/VCHL CC 0, 1, 3 with CS and unchanged without, signed against logical order with high-bit elements, VEC/VECL on the PoO's element, VTM's three CCs, the most negative element under VLC/VLP, counts of zero elements, ES 4 forms; invalid sizes `S0C6` with storage unchanged |
| `tests/integration/hlasm/test_vector_integer_arithmetic.py` | Every vector integer arithmetic family on the VM, read back with VSTM, with V1 equal to a source: wraparound and carry out at every size, the bit-127 carry forms, rounded averages, signed against logical high multiply on negative elements, multiply-and-add overflow, VMSL with each shift flag, Galois-field XOR folds, VCKSM's end-around carry, sums across, truncating divides and remainders, IDC zeros; the integer-divide exception's `S0DB`, VXC in the FPC and V1 unchanged; invalid M fields `S0C6` with storage unchanged |
| `tests/integration/hlasm/test_vector_register.py` | Every vector register-manipulation family on the VM, read back with VST, STG and IPM, with V1 equal to a source: masks with wrapping ranges, VLGV/VLVG at addresses past 4095, merges, permutes over both sources, packs saturating with CC 0, 1, 3 and unchanged without CS, replication, selection, sign extension, unpacks; invalid sizes and indexes `S0C6` with storage unchanged |
| `tests/integration/hlasm/test_conditional_select_count_mnemonics.py` | Every load/store-on-condition and SELECT extended spelling reaches its base mnemonic and Figure J-1 mask |
| `tests/unit/hlasm/test_interlocked_lowering.py` | Interlocked IR: the boundary check first, one compare that swaps or reloads, CAL's second-operand check only when loading, the load-and-operate stores and overflow check, TS, odd pairs abend `S0C6`, no SYMBOLIC; the PLO table's shape per code, GR0 and test-bit checks before a 62-way tree, PLO under EX lowered once |
| `tests/integration/hlasm/test_interlocked.py` | Every interlocked mnemonic on the VM: equal and unequal compares, pairs, CALGF zero extension, every CSST code and characteristic, overflow, carry and boolean CCs (zero CCs at 64 bits), R1 as base or R3, each boundary `S0C6` with storage unchanged |
| `tests/integration/hlasm/test_perform_locked_operation.py` | Every PLO function code on the VM, all compares equal and each one missed, from the tests' own reading of Figure 7-380 and a byte model: registers, all operand and parameter-list storage, unequal-results byte, CC; the test bit, GR0 bits 32-54, code 62, odd registers, misaligned D2, D4, list and listed operands with storage unchanged, EX of PLO |
| `tests/z390/test_perform_locked_operation_differential.py` | A PLO case per operation shape: the PoO expectation here, z390's `S0C1` pinned (`-m z390`) |
| `tests/z390/test_interlocked_differential.py` | Every interlocked case against z390; its missing CAL and CSST, unchecked boundaries and LAAL CC pinned (`-m z390`) |
| `tests/unit/hlasm/test_unicode_string_search_lowering.py` | Conversion and search IR: each form's unit widths read and written, no comparison on a byte image, the checks M3's W bit adds, odd pairs abend `S0C6`, GR0 checked before the search reads storage |
| `tests/integration/hlasm/test_unicode_string_search.py` | Every conversion and search mnemonic on the VM: output, lengths, addresses and CC 0-2; truncated characters, both operands ending together, W on and off for overlong, the 800, 10000 and 110000 bounds, surrogate, continuation and unpaired surrogates; SRST and SRSTU found, not found, end excluded, SRSTU's two-byte compare and odd end, bit 32; GR0 `S0C6` before any register changes |
| `tests/z390/test_unicode_string_search_differential.py` | SRST against z390; z390's `S0C1` on the conversions and SRSTU pinned (`-m z390`) |
| `tests/unit/hlasm/test_high_word_lowering.py` | High-word IR: the high or low word each form reads, R1's high word the only register written, which forms set the CC or take the `S0C8` check, BRCTH's target before its count, LFHAT's `S0C7` after its load |
| `tests/integration/hlasm/test_high_word.py` | Every high-word mnemonic and JCTH on the VM: results with the low word kept, CC 0-3, ALSIHN keeping the CC, negative immediates, signed against logical compares, masks 0 and partial, LMH and STMH wrapping, BRCTH wrap, LFHAT trap |
| `tests/z390/test_high_word_differential.py` | Every high-word case against z390; its `S0FF` for LFHAT and its ALSIH negative-immediate CC pinned (`-m z390`) |
| `tests/unit/hlasm/test_miscellaneous_lowering.py` | Miscellaneous IR: the CC, mask and registers SPM, IPM and EPSW touch; access-register moves through their region; LAM's boundary check first; clock forms call their builtin and ECTG fetches all operands first; hints lower to nothing, traps abend `S0D3`; the `S0C6` checks before any store; no SYMBOLIC |
| `tests/integration/hlasm/test_miscellaneous.py` | Every miscellaneous mnemonic on the VM with a fixed clock: registers, CC, abend; AR wrap and boundaries, CKSM tail and carry, ECAG selections, STFLE short, exact and complete, LCBB, STCK and STCKE order, MC under EX; `S0C8` end to end after SPM; boundary abends store nothing |
| `tests/z390/test_miscellaneous_differential.py` | Every miscellaneous case against z390; the instructions z390 does not execute, its clock CCs and STCKE bits, STFLE, unchecked AR boundaries and initial access registers pinned (`-m z390`) |
| `tests/unit/hlasm/test_packed_arithmetic_lowering.py` | Packed-decimal IR: `S0C6`, reads and `S0C7` (and DP's `S0CB`) before the first store, CC then `S0CA` after it; EX layouts; no SYMBOLIC |
| `tests/integration/hlasm/test_packed_arithmetic.py` | Every packed-decimal mnemonic on the VM: results, signs of zeros, CCs, overlap, SRP shifts and rounding, EX lengths; `S0C6`, `S0C7`, `S0CA`, `S0CB`; an executed SRP's bad rounding digit; the stored overflow result and the untouched operand after an abend, `S0C6` included |
| `tests/z390/test_packed_arithmetic_differential.py` | Every packed-decimal case against z390; SRP negative rounding and I3 check, negative zeros, CC at `S0CA` pinned (`-m z390`) |
| `tests/unit/hlasm/test_packed_compare_test_lowering.py` | CP and TP IR: CP's reads and `S0C7` before its CC, TP's read then CC, no store; EX layouts; no SYMBOLIC |
| `tests/integration/hlasm/test_packed_compare_test.py` | CP and TP on the VM: CP at unequal lengths, -0 against +0, alternate signs, 31 digits, `S0C7` on either operand with the CC kept; TP CC 0-3 at 1, 2, 3 and 16 bytes, every valid sign; EX lengths; storage unchanged |
| `tests/z390/test_packed_compare_test_differential.py` | Every CP and TP case against z390 (`-m z390`) |
| `tests/unit/hlasm/test_decimal_conversion_lowering.py` | Decimal conversion IR: CVB's `S0C7`, R1 write, then `S0C9`; CVBG's `S0C9` before its write; `S0C6` before the first store; UNPKA/UNPKU set the CC last; EX layouts; no SYMBOLIC |
| `tests/integration/hlasm/test_decimal_conversion.py` | Every decimal conversion mnemonic on the VM: CVB limits, -0, `S0C7`, `S0C9` with the low word stored; CVBG `S0C9` suppressed; CVD/CVDG signs and the high word; PACK and UNPK truncation, padding and overlap; PKA/PKU/UNPKA/UNPKU at full length, CCs set over a preset one and `S0C6` with nothing stored; EX lengths |
| `tests/z390/test_decimal_conversion_differential.py` | Every decimal conversion case against z390; CVB `S0C9`, CVDY, PKU and UNPKU pinned (`-m z390`) |
| `tests/unit/hlasm/test_edit_lowering.py` | Edit IR: the source read and `S0C7` before the first store, the CC after, EDMK's GR1 last; EX layout; no SYMBOLIC |
| `tests/integration/hlasm/test_edit.py` | ED and EDMK on the VM: amount mask with CR, zero suppression, field separators, CC from the last field, alternate signs, a fill byte that is X'20' or X'21', a pending digit across X'22', a first digit with a plus code, GR1 marked or kept; EX length; `S0C7` with the pattern, CC and GR1 unchanged |
| `tests/z390/test_edit_differential.py` | Every edit case against z390 (`-m z390`) |
| `tests/unit/hlasm/test_floating_point_support_lowering.py` | Floating-point-support IR: FPR offsets (stride 16) and widths, short forms on 4 bytes; invalid pairs abend before any access; FPC checks before the FPC store, the LFAS/SFASR trap after it; no SYMBOLIC |
| `tests/integration/hlasm/test_floating_point_support.py` | Every floating-point-support mnemonic on the VM through GRs: moves, low word kept, sign forms, FPC loads and rounding modes, `S0C6` with the FPC unchanged, each Figure 9-21 DXC with `S0C7`; EX of LER |
| `tests/z390/test_floating_point_support_differential.py` | Every floating-point-support case against z390; its initial FPC, short loads, HFP sign forms, missing checks and signaling pinned (`-m z390`) |
| `tests/unit/hlasm/test_bfp_builtins.py` | BFP builtins: fields to values and back for every class; each builtin family's value, scaled value, trap, flags, DXCs and CC |
| `tests/unit/hlasm/test_bfp_arithmetic_lowering.py` | BFP IR: operands in argument order, one builtin call, then the trap ladder; static `S0C6` before any access; compares, test data class and sign forms without a builtin; no SYMBOLIC in all 70 |
| `tests/integration/hlasm/test_bfp_arithmetic.py` | Every BFP arithmetic mnemonic on the VM: result images, CC and FPC flags; signed and extended compares and every TCEB, TCDB and TCXB class bit; each trap's delivered value, DXC and `S0C7`; fused NaN order and 0 x inf with an SNaN addend |
| `tests/z390/test_bfp_arithmetic_differential.py` | Every BFP arithmetic case against z390; its faults pinned (`-m z390`) |
| `tests/unit/hlasm/test_bfp_conversion_lowering.py` | BFP conversion IR: builtin forms call then run the ladder; exact forms call nothing; static `S0C6` before any access; no SYMBOLIC |
| `tests/integration/hlasm/test_bfp_conversion.py` | Every BFP conversion mnemonic on the VM: GR or FPR results, CC, FPC flags, and trap DXCs and `S0C7` |
| `tests/z390/test_bfp_conversion_differential.py` | Every BFP conversion case against z390; its faults pinned (`-m z390`) |
| `tests/unit/hlasm/test_hfp_builtins.py` | HFP builtins: fields, the characteristic modulo 128 and condition bits for each family; compare's CC |
| `tests/unit/hlasm/test_hfp_arithmetic_lowering.py` | HFP IR: operands in argument order, one call, then the program-mask ladder; sign forms without a call; invalid pairs abend `S0C6` before any access; no SYMBOLIC in all 81 |
| `tests/integration/hlasm/test_hfp_arithmetic.py` | Every HFP arithmetic mnemonic on the VM: result images and CC; each exception's stored or suppressed result and abend, with its mask bit on and off |
| `tests/z390/test_hfp_arithmetic_differential.py` | Every HFP arithmetic case against z390; its faults pinned (`-m z390`) |
| `tests/unit/hlasm/test_hfp_conversion_lowering.py` | HFP conversion IR: rounding forms read M3 and the operand, call, store and set the CC; IR forms call nothing; static `S0C6` before any access; no SYMBOLIC |
| `tests/integration/hlasm/test_hfp_conversion.py` | Every HFP conversion mnemonic on the VM: GR or FPR results and CC; LOAD ROUNDED overflow stores, then `S0CC` |
| `tests/z390/test_hfp_conversion_differential.py` | Every HFP conversion case against z390; its faults pinned (`-m z390`) |
| `tests/unit/hlasm/test_dpd_codec.py` | DPD codec IR: all 1000 declets against figures 20-32 and 20-33, the 24 noncanonical declets, each format's fields and canonical encoding |
| `tests/unit/hlasm/test_program_functions.py` | A DFP program defines each codec function it calls once; a program without DFP defines none; a function called only from another body is defined too |
| `tests/unit/hlasm/test_dfp_builtins.py` | DFP builtins: fields to values and back for every kind; each family's value, scaled value, trap, flags, DXCs and CC |
| `tests/unit/hlasm/test_dfp_arithmetic_lowering.py` | DFP IR: operands decoded in argument order, one builtin call, the ladder, then encode and store; the A forms' modifier replaces the FPC read; invalid pairs abend `S0C6` before any access; no SYMBOLIC |
| `tests/integration/hlasm/test_dfp_arithmetic.py` | Every DFP arithmetic mnemonic on the VM: images, CC and FPC flags; the FPC DFP mode; the tininess edge; each trap's delivered value, DXC and `S0C7`, quantum traps included |
| `tests/z390/test_dfp_arithmetic_differential.py` | Every DFP arithmetic case against z390; its faults pinned (`-m z390`) |
| `tests/z390/test_dfp_conversion_differential.py` | Every DFP conversion and PFPO case against z390; its faults pinned (`-m z390`) |
| `tests/unit/hlasm/test_pfpo_builtins.py`, `test_pfpo_lowering.py` | PFPO: the builtin's formats, controls and scaling exponent; the lowering's decoders, encoders, single call and GR1 store |
| `tests/unit/hlasm/test_decimal_lanes.py` | Decimal lanes: digits spread into packed and zoned lanes and combine back; a digit above 9 is caught in any lane |
| `tests/unit/hlasm/test_dfp_conversion_lowering.py` | DFP conversion IR: the operand read and decoded, one builtin call, the ladder, then the GR or encoded FPR store; invalid pairs abend `S0C6` before any access; no SYMBOLIC |
| `tests/integration/hlasm/test_dfp_conversion.py` | Every DFP conversion mnemonic and PFPO on the VM: results, CC and FPC flags; each trap's delivered value, DXC and `S0C7`; PFPO's GR1 return code on a trap; EX of an RSL-b form |
| `tests/z390/test_conditional_select_count_differential.py` | Every conditional, select and count case against z390; the instructions z390 does not execute and its whole-register SELFHR pinned (`-m z390`) |
