# pyright: standard
"""Partition the z/Architecture problem-state che4z machine instructions, bar the system set, into opcode units; run as `python -m scripts.hlasm_classify_opcodes`."""

from __future__ import annotations

import logging
import os
import subprocess
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import hlasm_asg
from hlasm_asg.instruction_table.architecture_level import ArchitectureLevel
from hlasm_asg.instruction_table.instruction_table import InstructionTable
from hlasm_asg.instruction_table.machine_instruction_row import MachineInstructionRow
from hlasm_asg.instruction_table.privilege import Privilege
from hlasm_asg.opcode_unit import OpcodeUnit
from hlasm_asg.opcode_units import OpcodeUnits

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(hlasm_asg.__file__).parent / "opcode_units.json"

ARCHITECTURES_WITHOUT_Z = frozenset(
    {
        ArchitectureLevel.ESA_XA,
        ArchitectureLevel.ESA_XA_370,
        ArchitectureLevel.UNI_370,
        ArchitectureLevel.UNI_370_DOS,
    }
)

SIE_LINKAGE_STACK_ASN_MEASUREMENT_GUARDED_STORAGE = frozenset(
    {
        "SIE",
        "BAKR",
        "PR",
        "EREG",
        "EREGG",
        "ESTA",
        "MSTA",
        "SSAR",
        "SSAIR",
        "TAR",
        "BSG",
        "ECCTR",
        "EPCTR",
        "ECPGA",
        "LCCTL",
        "LPCTL",
        "LSCTL",
        "LPP",
        "QCTRI",
        "QSI",
        "SCCTR",
        "SPCTR",
        "STCCTM",
        "LGSC",
        "STGSC",
    }
)

VECTOR_FORMATS = frozenset(
    {
        *(f"VRI-{letter}" for letter in "abcdefghijkl"),
        *(f"VRR-{letter}" for letter in "abcdefghijk"),
        *(f"VRS-{letter}" for letter in "abcd"),
        "VRV",
        "VRX",
        "VSI",
    }
)


def _unit(name: str, title: str, wave: int, mnemonics: str) -> OpcodeUnit:
    return OpcodeUnit(
        name=name, title=title, wave=wave, mnemonics=tuple(mnemonics.split())
    )


LISTED_UNITS = (
    _unit(
        "load-store",
        "Load and store",
        1,
        "L LR LG LGR LGF LGFR LH LHR LGH LGHR LHY LY LB LBR LGB LGBR "
        "LLC LLCR LLGC LLGCR LLH LLHR LLGH LLGHR LLGF LLGFR LLGT LLGTR "
        "LLZRGF LZRF LZRG ST STG STY STH STHY STC STCY "
        "LM LMG LMY STM STMG STMY IC ICY ICM ICMY STCM STCMY "
        "LRV LRVR LRVG LRVGR LRVH STRV STRVG STRVH LMD LGG LLGFSG "
        "LRL LGRL LGFRL LHRL LGHRL LLHRL LLGHRL LLGFRL STRL STGRL STHRL",
    ),
    _unit(
        "load-address-immediate",
        "Load address and immediates",
        1,
        "LA LAY LARL LAE LAEY LXAB LXAF LXAG LXAH LXAQ "
        "LLXAB LLXAF LLXAG LLXAH LLXAQ LHI LGHI LGFI "
        "LLIHH LLIHL LLILH LLILL LLIHF LLILF IIHH IIHL IILH IILL IIHF IILF",
    ),
    _unit(
        "signed-add-subtract",
        "Signed add and subtract",
        1,
        "A AR AG AGR AGF AGFR AH AHY AGH AY AHI AGHI AFI AGFI ARK AGRK "
        "AHIK AGHIK ASI AGSI S SR SG SGR SGF SGFR SH SHY SGH SY SRK SGRK",
    ),
    _unit(
        "logical-add-subtract",
        "Logical add and subtract with carry and borrow",
        1,
        "AL ALR ALG ALGR ALGF ALGFR ALY ALFI ALGFI ALRK ALGRK ALHSIK ALGHSIK "
        "ALSI ALGSI ALC ALCR ALCG ALCGR SL SLR SLG SLGR SLGF SLGFR SLY "
        "SLFI SLGFI SLRK SLGRK SLB SLBR SLBG SLBGR",
    ),
    _unit(
        "multiply-divide",
        "Multiply and divide",
        1,
        "M MR MH MHI MHY MFY MS MSR MSY MSG MSGR MSGF MSGFR MSFI MSGFI "
        "MSC MSGC MSRKC MSGRKC MG MGH MGRK MGHI ML MLR MLG MLGR "
        "D DR DL DLR DLG DLGR DSG DSGR DSGF DSGFR",
    ),
    _unit(
        "compare",
        "Compare, signed and logical",
        1,
        "C CR CG CGR CGF CGFR CH CHY CGH CHI CGHI CFI CGFI CHSI CGHSI CHHSI "
        "CY CRL CGRL CGFRL CHRL CGHRL CL CLR CLG CLGR CLGF CLGFR CLY CLFI "
        "CLGFI CLFHSI CLGHSI CLHHSI CLI CLIY CLRL CLGRL CLGFRL CLHRL CLGHRL "
        "CLM CLMY",
    ),
    _unit(
        "compare-branch-trap",
        "Compare-and-branch and compare-and-trap",
        1,
        "CRJ CGRJ CLRJ CLGRJ CIJ CGIJ CLIJ CLGIJ CRB CGRB CLRB CLGRB "
        "CIB CGIB CLIB CLGIB CRT CGRT CLRT CLGRT CIT CGIT CLFIT CLGIT "
        "CLT CLGT LAT LGAT LLGFAT LLGTAT",
    ),
    _unit(
        "boolean",
        "Boolean AND, OR and exclusive OR",
        1,
        "N NR NG NGR NY NRK NGRK NC NI NIY NIHH NIHL NILH NILL NIHF NILF "
        "O OR OG OGR OY ORK OGRK OC OI OIY OIHH OIHL OILH OILL OIHF OILF "
        "X XR XG XGR XY XRK XGRK XC XI XIY XIHF XILF "
        "NCRK NCGRK NNRK NNGRK NORK NOGRK NXRK NXGRK OCRK OCGRK",
    ),
    _unit(
        "shift-rotate",
        "Shifts and rotates, including the RISBG family",
        1,
        "SLA SLAG SLAK SLDA SLDL SLL SLLG SLLK SRA SRAG SRAK SRDA SRDL SRL "
        "SRLG SRLK RLL RLLG RISBG RISBGN RISBHG RISBLG RNSBG ROSBG RXSBG",
    ),
    _unit(
        "branch-on-condition",
        "Branch on condition and its extended mnemonics",
        1,
        "BC BCR BRC BRCL BIC BPP BPRP",
    ),
    _unit(
        "branch-and-link",
        "Branch and link, branch and save, addressing mode",
        1,
        "BAL BALR BAS BASR BRAS BRASL BASSM BSM SAM24 SAM31 SAM64 TAM",
    ),
    _unit(
        "loop-branch",
        "Branch on count and branch on index",
        1,
        "BCT BCTR BCTG BCTGR BRCT BRCTG BXH BXLE BXHG BXLEG " "BRXH BRXLE BRXHG BRXLG",
    ),
    _unit(
        "ss-move",
        "Storage-to-storage and storage-immediate moves",
        1,
        "MVC MVCL MVCLE MVCLU MVI MVIY MVN MVZ MVO MVCIN MVST MVCRL "
        "MVHHI MVHI MVGHI",
    ),
    _unit(
        "ss-compare",
        "Storage-to-storage compares",
        1,
        "CLC CLCL CLCLE CLCLU CLST CUSE",
    ),
    _unit(
        "translate",
        "Translate",
        1,
        "TR TRT TRTR TRE TROO TROT TRTO TRTT TRTE TRTRE",
    ),
    _unit(
        "test-under-mask",
        "Test under mask",
        1,
        "TM TMY TMH TML TMHH TMHL TMLH TMLL",
    ),
    _unit("execute", "Execute", 1, "EX EXRL"),
    _unit(
        "load-test-sign",
        "Load and test, positive, negative and complement",
        1,
        "LTR LT LTG LTGR LTGF LTGFR LPR LPGR LPGFR LNR LNGR LNGFR " "LCR LCGR LCGFR",
    ),
    _unit(
        "conditional-select-count",
        "Conditional load and store, select, population and bit counts",
        1,
        "LOC LOCG LOCR LOCGR LOCFH LOCFHR LOCHI LOCGHI LOCHHI "
        "STOC STOCG STOCFH SELR SELGR SELFHR POPCNT FLOGR "
        "CLZG CTZG BDEPG BEXTG",
    ),
    _unit(
        "interlocked",
        "Interlocked update",
        1,
        "CS CSY CSG CDS CDSY CDSG CSST PLO LAA LAAG LAAL LAALG LAN LANG "
        "LAO LAOG LAX LAXG TS LPD LPDG LPQ STPQ CAL CALG CALGF",
    ),
    _unit(
        "unicode-string-search",
        "Unicode conversion and string search",
        1,
        "CU12 CU14 CU21 CU24 CU41 CU42 CUTFU CUUTF SRST SRSTU",
    ),
    _unit(
        "high-word",
        "High-word",
        1,
        "AHHHR AHHLR ALHHHR ALHHLR SHHHR SHHLR SLHHHR SLHHLR AIH ALSIH ALSIHN "
        "CHHR CHLR CHF CIH CLHHR CLHLR CLHF CLIH LBH LHH LLCH LLHH LFH LFHAT "
        "STCH STHH STFH BRCTH LMH STMH ICMH CLMH STCMH",
    ),
    _unit(
        "miscellaneous",
        "Miscellaneous general instructions and access registers",
        1,
        "IPM SPM EPSW STCK STCKE STCKF ECTG STFLE ECAG TRAP2 TRAP4 CKSM SVC MC "
        "NIAI PFD PFDRL LCBB CPYA EAR SAR LAM LAMY STAM STAMY",
    ),
    _unit(
        "packed-arithmetic",
        "Packed-decimal arithmetic",
        1,
        "AP SP MP DP ZAP SRP",
    ),
    _unit("packed-compare-test", "Packed-decimal compare and test", 1, "CP TP"),
    _unit(
        "decimal-conversion",
        "Decimal conversion",
        1,
        "PACK UNPK PKA PKU UNPKA UNPKU CVB CVBY CVBG CVD CVDY CVDG",
    ),
    _unit("edit", "Edit", 1, "ED EDMK"),
    _unit(
        "fp-support",
        "Floating-point registers, load and store, and support",
        1,
        "LD LDY LE LEY LDR LER LXR STD STDY STE STEY LZDR LZER LZXR "
        "LDGR LGDR CPSDR LCDFR LNDFR LPDFR EFPC SFPC LFPC STFPC SFASR LFAS "
        "SRNM SRNMB SRNMT PFPO",
    ),
    _unit(
        "bfp-arithmetic",
        "Binary floating-point arithmetic",
        1,
        "ADB ADBR AEB AEBR AXBR SDB SDBR SEB SEBR SXBR MDB MDBR MEEB MEEBR "
        "MXBR MDEB MDEBR MXDB MXDBR DDB DDBR DEB DEBR DXBR MADB MADBR MAEB "
        "MAEBR MSDB MSDBR MSEB MSEBR SQDB SQDBR SQEB SQEBR SQXBR DIDBR DIEBR "
        "CDB CDBR CEB CEBR CXBR KDB KDBR KEB KEBR KXBR LTDBR LTEBR LTXBR "
        "LCDBR LCEBR LCXBR LNDBR LNEBR LNXBR LPDBR LPEBR LPXBR TCEB TCDB TCXB "
        "FIDBR FIDBRA FIEBR FIEBRA FIXBR FIXBRA",
    ),
    _unit(
        "bfp-conversion",
        "Binary floating-point conversions",
        1,
        "LDEB LDEBR LXDB LXDBR LXEB LXEBR LEDBR LEDBRA LDXBR LDXBRA LEXBR LEXBRA "
        "CDFBR CDFBRA CDGBR CDGBRA CEFBR CEFBRA CEGBR CEGBRA CXFBR CXFBRA "
        "CXGBR CXGBRA CDLFBR CDLGBR CELFBR CELGBR CXLFBR CXLGBR "
        "CFDBR CFDBRA CFEBR CFEBRA CFXBR CFXBRA CGDBR CGDBRA CGEBR CGEBRA "
        "CGXBR CGXBRA CLFDBR CLFEBR CLFXBR CLGDBR CLGEBR CLGXBR",
    ),
    _unit(
        "hfp-arithmetic",
        "Hexadecimal floating-point arithmetic",
        1,
        "AD ADR AE AER AXR AU AUR AW AWR SD SDR SE SER SXR SU SUR SW SWR "
        "MD MDR ME MER MDE MDER MEE MEER MXR MXD MXDR MY MYR MYH MYHR MYL MYLR "
        "MAY MAYR MAYH MAYHR MAYL MAYLR MAD MADR MAE MAER MSD MSDR MSE MSER "
        "DD DDR DE DER DXR SQD SQDR SQE SQER SQXR HDR HER CD CDR CE CER CXR "
        "LTDR LTER LTXR LCDR LCER LCXR LNDR LNER LNXR LPDR LPER LPXR "
        "FIDR FIER FIXR",
    ),
    _unit(
        "hfp-conversion",
        "Hexadecimal floating-point conversions",
        1,
        "LDE LDER LXD LXDR LXE LXER LEDR LRER LDXR LEXR LRDR "
        "CDFR CDGR CEFR CEGR CXFR CXGR CFDR CFER CFXR CGDR CGER CGXR "
        "THDR THDER TBDR TBEDR",
    ),
    _unit(
        "dfp-arithmetic",
        "Decimal floating-point arithmetic",
        1,
        "ADTR ADTRA AXTR AXTRA SDTR SDTRA SXTR SXTRA MDTR MDTRA MXTR MXTRA "
        "DDTR DDTRA DXTR DXTRA CDTR CXTR KDTR KXTR CEDTR CEXTR LTDTR LTXTR "
        "TDCDT TDCET TDCXT TDGDT TDGET TDGXT QADTR QAXTR RRDTR RRXTR "
        "SLDT SLXT SRDT SRXT FIDTR FIXTR EEDTR EEXTR ESDTR ESXTR IEDTR IEXTR",
    ),
    _unit(
        "dfp-conversion",
        "Decimal floating-point conversions",
        1,
        "LDETR LXDTR LEDTR LDXTR CDGTR CDGTRA CXGTR CXGTRA CDFTR CXFTR "
        "CDLFTR CDLGTR CXLFTR CXLGTR CGDTR CGDTRA CGXTR CGXTRA CFDTR CFXTR "
        "CLFDTR CLFXTR CLGDTR CLGXTR CDUTR CXUTR CUDTR CUXTR CDSTR CXSTR "
        "CSDTR CSXTR CDPT CXPT CPDT CPXT CDZT CXZT CZDT CZXT",
    ),
    _unit(
        "vector-decimal",
        "Vector packed decimal",
        2,
        "VAP VCP VCVB VCVBG VCVD VCVDG VDP VLIP VLRL VLRLR VMP VMSP VPKZ "
        "VPSOP VRP VSDP VSP VSRP VSTRL VSTRLR VTP VUPKZ VCLZDP VPKZR VSCHP "
        "VSCSHP VSRPR VUPKZH VUPKZL VCSPH VCVBQ VCVDQ VTZ",
    ),
    _unit(
        "nnpa",
        "Neural-network processing assist",
        2,
        "NNPA VCNF VCLFNH VCLFNL VCFN VCRNF",
    ),
    _unit(
        "crypto",
        "Message-security assist",
        2,
        "KM KMC KMAC KMF KMO KMCTR KMA KIMD KLMD PCC PPNO PRNO KDSA",
    ),
    _unit(
        "transactional",
        "Transactional execution",
        2,
        "TBEGIN TBEGINC TEND TABORT ETND NTSTG PPA",
    ),
    _unit(
        "sort-compression",
        "Sort, compression and deflate",
        2,
        "CFC UPT CMPSC SORTL DFLTCC",
    ),
)

LISTED = frozenset(m for unit in LISTED_UNITS for m in unit.mnemonics)


def _instruction_table() -> InstructionTable:
    completed = subprocess.run(
        [os.environ["HLASM_AST_BRIDGE"], "--instruction-table"],
        capture_output=True,
        check=True,
        text=True,
    )
    return InstructionTable.model_validate_json(completed.stdout)


def _machine_rows(
    table: InstructionTable,
    privilege: Privilege,
) -> tuple[MachineInstructionRow, ...]:
    return tuple(
        row
        for row in table.instructions
        if isinstance(row, MachineInstructionRow) and row.privileged == privilege
    )


def _distinct(rows: Sequence[MachineInstructionRow]) -> tuple[str, ...]:
    return tuple(sorted({row.mnemonic for row in rows}))


def _covered(
    rows: Sequence[MachineInstructionRow],
) -> tuple[MachineInstructionRow, ...]:
    return tuple(
        row
        for row in rows
        if row.arch not in ARCHITECTURES_WITHOUT_Z
        and row.mnemonic not in SIE_LINKAGE_STACK_ASN_MEASUREMENT_GUARDED_STORAGE
    )


def _vector_unit(rows: Sequence[MachineInstructionRow]) -> OpcodeUnit:
    return OpcodeUnit(
        name="vector",
        title="Vector",
        wave=2,
        mnemonics=_distinct(
            [
                row
                for row in rows
                if row.format in VECTOR_FORMATS and row.mnemonic not in LISTED
            ]
        ),
    )


def _sorted_unit(unit: OpcodeUnit) -> OpcodeUnit:
    return unit.model_copy(update={"mnemonics": tuple(sorted(unit.mnemonics))})


def _classify(rows: Sequence[MachineInstructionRow]) -> OpcodeUnits:
    vector = _vector_unit(rows)
    wave_1 = tuple(unit for unit in LISTED_UNITS if unit.wave == 1)
    wave_2 = tuple(unit for unit in LISTED_UNITS if unit.wave == 2)
    return OpcodeUnits(
        units=tuple(_sorted_unit(unit) for unit in (*wave_1, vector, *wave_2))
    )


def _report(units: OpcodeUnits, rows: Sequence[MachineInstructionRow]) -> None:
    assigned = Counter(m for unit in units.units for m in unit.mnemonics)
    problem = set(_distinct(rows))
    logger.info("unassigned: %s", sorted(problem - set(assigned)))
    logger.info("listed but not covered: %s", sorted(set(assigned) - problem))
    logger.info("in two units: %s", sorted(m for m, n in assigned.items() if n > 1))
    logger.info("units: %d, mnemonics: %d", len(units.units), len(problem))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    table = _instruction_table()
    problem_state = _machine_rows(table, Privilege.NOT_PRIVILEGED)
    rows = _covered(problem_state)
    logger.info(
        "excluded: %s",
        sorted(set(_distinct(problem_state)) - set(_distinct(rows))),
    )
    units = _classify(rows)
    _report(units, rows)
    logger.info(
        "conditionally privileged: %s",
        list(_distinct(_machine_rows(table, Privilege.CONDITIONALLY_PRIVILEGED))),
    )
    OUTPUT_PATH.write_text(units.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
