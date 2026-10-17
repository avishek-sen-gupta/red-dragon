package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.CompilationUnit;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.metamodel.ProgramUnit;
import io.proleap.cobol.asg.metamodel.data.DataDivision;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.file.FileDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.file.FileSection;
import io.proleap.cobol.asg.metamodel.data.linkage.LinkageSection;
import io.proleap.cobol.asg.metamodel.data.localstorage.LocalStorageSection;
import io.proleap.cobol.asg.metamodel.data.workingstorage.WorkingStorageSection;
import io.proleap.cobol.asg.metamodel.environment.EnvironmentDivision;
import io.proleap.cobol.asg.metamodel.environment.configuration.ConfigurationSection;
import io.proleap.cobol.asg.metamodel.environment.configuration.object.CollatingSequenceClause;
import io.proleap.cobol.asg.metamodel.environment.specialnames.AlphabetClause;
import io.proleap.cobol.asg.metamodel.environment.specialnames.CurrencySignClause;
import io.proleap.cobol.asg.metamodel.environment.specialnames.SpecialNamesParagraph;
import io.proleap.cobol.asg.metamodel.environment.inputoutput.InputOutputSection;
import io.proleap.cobol.asg.metamodel.environment.inputoutput.filecontrol.FileControlEntry;
import io.proleap.cobol.asg.metamodel.environment.inputoutput.filecontrol.FileControlParagraph;
import io.proleap.cobol.asg.metamodel.identification.IdentificationDivision;
import io.proleap.cobol.asg.metamodel.procedure.Paragraph;
import io.proleap.cobol.asg.metamodel.procedure.ProcedureDivision;
import io.proleap.cobol.asg.metamodel.procedure.Section;
import io.proleap.cobol.asg.metamodel.procedure.Statement;
import io.proleap.cobol.asg.metamodel.procedure.ByReference;
import io.proleap.cobol.asg.metamodel.procedure.ByValue;
import io.proleap.cobol.asg.metamodel.procedure.UsingClause;
import io.proleap.cobol.asg.metamodel.procedure.UsingParameter;
import io.proleap.cobol.CobolParser;
import io.proleap.cobol.asg.metamodel.procedure.declaratives.Declaratives;
import io.proleap.cobol.asg.metamodel.procedure.declaratives.Declarative;
import io.proleap.cobol.asg.metamodel.procedure.use.AfterOn;
import io.proleap.cobol.asg.metamodel.procedure.use.UseAfterStatement;
import io.proleap.cobol.asg.metamodel.procedure.use.UseStatement;
import io.proleap.cobol.asg.metamodel.call.Call;

import java.util.ArrayList;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.tree.ParseTree;
import org.antlr.v4.runtime.tree.TerminalNode;
import java.util.Collection;
import java.util.List;
import java.util.logging.Logger;

/**
 * Top-level ASG serializer: walks a ProLeap {@link Program} and produces
 * a JSON object matching the RedDragon {@code CobolASG} contract.
 *
 * <p>Output structure:
 * <pre>
 * {
 *   "data_fields": [...],          // WORKING-STORAGE SECTION
 *   "linkage_fields": [...],       // LINKAGE SECTION (optional)
 *   "procedure_using": [{"name": "...", "type": "REFERENCE"|"VALUE"}],
 *                                  // PROCEDURE DIVISION USING, in order (optional)
 *   "local_storage_fields": [...], // LOCAL-STORAGE SECTION (optional)
 *   "data_division_exec_sql": [...], // EXEC SQL entries outside PROCEDURE
 *                                     // DIVISION, e.g. DECLARE CURSOR in
 *                                     // WORKING-STORAGE (optional)
 *   "sections": [{"name": "...", "paragraphs": [...]}],
 *   "paragraphs": [{"name": "...", "statements": [...]}]
 * }
 * </pre>
 */
public final class AsgSerializer {

    private static final Logger LOG = Logger.getLogger(AsgSerializer.class.getName());

    private AsgSerializer() {
    }

    /**
     * Serializes a ProLeap Program to a CobolASG-compatible JSON object.
     *
     * @param program the parsed ProLeap Program
     * @return JSON object matching CobolASG.from_dict() contract
     */
    public static JsonObject serialize(Program program) {
        JsonObject asg = new JsonObject();

        CompilationUnit cu = program.getCompilationUnit();
        if (cu == null) {
            LOG.warning("No CompilationUnit found in program");
            return asg;
        }

        ProgramUnit pu = cu.getProgramUnit();
        if (pu == null) {
            LOG.warning("No ProgramUnit found in CompilationUnit");
            return asg;
        }

        IdentificationDivision id = pu.getIdentificationDivision();
        if (id != null && id.getProgramIdParagraph() != null) {
            asg.addProperty("program_id", id.getProgramIdParagraph().getName());
        } else {
            asg.addProperty("program_id", cu.getName());
        }

        NumericLiteralText.useDecimalPointIsComma(hasDecimalPointIsComma(pu));
        serializeDataDivision(pu, asg);
        serializeProcedureDivision(pu, asg);
        asg.add("file_control", serializeFileControl(pu));
        JsonObject specialNames = serializeSpecialNames(pu);
        if (specialNames.size() > 0) {
            asg.add("special_names", specialNames);
        }

        return asg;
    }

    /**
     * Serializes the SPECIAL-NAMES paragraph clauses RedDragon consumes, with
     * OBJECT-COMPUTER's PROGRAM COLLATING SEQUENCE beside them.
     *
     * <p>The ALPHABET clause the program collating sequence names is emitted as
     * {@code "program_collating_sequence"}.
     *
     * <p>For CURRENCY SIGN IS, ProLeap's {@code CurrencySignClause}
     * exposes both {@code getCurrencyLiteral()} and
     * {@code getPictureSymbolLiteral()}; both are emitted so the Python side can
     * REFUSE the multi-character PICTURE SYMBOL form loudly rather than silently
     * mis-size fields — a multi-character currency literal changes every
     * affected field's byte width (red-dragon-3o5f).
     *
     * <p>DECIMAL-POINT IS COMMA is emitted as {@code "decimal_point_is_comma"}.
     * Numeric literals are already written with a period by then (see
     * {@link NumericLiteralText}); the flag is what the pictures need.
     *
     * <p>Returns an EMPTY object when there is no SPECIAL-NAMES paragraph, so
     * the caller can omit the key entirely and Python keeps its '$' default.
     */
    private static JsonObject serializeSpecialNames(ProgramUnit pu) {
        JsonObject result = new JsonObject();
        EnvironmentDivision env = pu.getEnvironmentDivision();
        if (env == null) return result;
        SpecialNamesParagraph snp = env.getSpecialNamesParagraph();
        if (snp == null) return result;
        serializeProgramCollatingSequence(env, snp, result);
        serializeSwitches(snp, result);
        serializeClasses(snp, result);
        if (snp.getDecimalPointClause() != null) {
            result.addProperty("decimal_point_is_comma", true);
        }
        CurrencySignClause csc = snp.getCurrencySignClause();
        if (csc == null) return result;
        if (csc.getCurrencyLiteral() != null) {
            result.addProperty("currency_sign",
                    literalText(csc.getCurrencyLiteral()));
        }
        if (csc.getPictureSymbolLiteral() != null) {
            result.addProperty("currency_picture_symbol",
                    literalText(csc.getPictureSymbolLiteral()));
        }
        return result;
    }

    /**
     * Each implementor switch clause ({@code environment-name IS mnemonic-name
     * ON STATUS IS condition-1 OFF STATUS IS condition-2}) as its environment
     * name, mnemonic name and the two status condition-names, each empty when
     * not written. ProLeap's ASG drops these clauses, so they are read from the
     * parse tree.
     */
    private static void serializeSwitches(SpecialNamesParagraph snp, JsonObject result) {
        if (!(snp.getCtx() instanceof CobolParser.SpecialNamesParagraphContext ctx)) return;
        JsonArray switches = new JsonArray();
        for (CobolParser.SpecialNameClauseContext clause : ctx.specialNameClause()) {
            if (clause.environmentSwitchNameClause() != null) {
                switches.add(serializeSwitch(clause.environmentSwitchNameClause()));
            }
        }
        if (switches.size() > 0) {
            result.add("switches", switches);
        }
    }

    private static JsonObject serializeSwitch(CobolParser.EnvironmentSwitchNameClauseContext ctx) {
        JsonObject sw = new JsonObject();
        sw.addProperty("environment_name", upperText(ctx.environmentName()));
        sw.addProperty("mnemonic_name", upperText(ctx.mnemonicName()));
        sw.addProperty("on_condition", "");
        sw.addProperty("off_condition", "");
        CobolParser.EnvironmentSwitchNameSpecialNamesStatusPhraseContext phrase =
                ctx.environmentSwitchNameSpecialNamesStatusPhrase();
        if (phrase == null) return sw;
        String status = "";
        for (ParseTree child : phrase.children) {
            if (child instanceof TerminalNode token
                    && (token.getSymbol().getType() == CobolParser.ON
                        || token.getSymbol().getType() == CobolParser.OFF)) {
                status = token.getSymbol().getType() == CobolParser.ON ? "on_condition" : "off_condition";
            } else if (child instanceof CobolParser.ConditionContext condition) {
                sw.addProperty(status, condition.getText().toUpperCase());
            }
        }
        return sw;
    }

    /**
     * Each CLASS clause as its class-name and its literals in source order,
     * each tagged NONE or THRU like an ALPHABET literal. ProLeap's ASG keeps
     * only one CLASS clause, so they are read from the parse tree. A clause
     * with an operand that is not a literal (an unsubstituted placeholder) is
     * left out, so its class-name stays undefined.
     */
    private static void serializeClasses(SpecialNamesParagraph snp, JsonObject result) {
        if (!(snp.getCtx() instanceof CobolParser.SpecialNamesParagraphContext ctx)) return;
        JsonArray classes = new JsonArray();
        for (CobolParser.SpecialNameClauseContext clause : ctx.specialNameClause()) {
            CobolParser.ClassClauseContext cls = clause.classClause();
            if (cls != null && classLiteralsOnly(cls)) {
                classes.add(serializeClass(cls));
            }
        }
        if (classes.size() > 0) {
            result.add("classes", classes);
        }
    }

    private static boolean classLiteralsOnly(CobolParser.ClassClauseContext cls) {
        for (CobolParser.ClassClauseThroughContext through : cls.classClauseThrough()) {
            if (through.classClauseFrom().literal() == null
                    || (through.classClauseTo() != null && through.classClauseTo().literal() == null)) {
                LOG.warning("CLASS " + cls.className().getText() + " has a non-literal operand; left undefined");
                return false;
            }
        }
        return true;
    }

    private static JsonObject serializeClass(CobolParser.ClassClauseContext cls) {
        JsonObject result = new JsonObject();
        result.addProperty("name", cls.className().getText().toUpperCase());
        JsonArray items = new JsonArray();
        for (CobolParser.ClassClauseThroughContext through : cls.classClauseThrough()) {
            items.add(alphabetItem(through.classClauseFrom().literal(), "NONE"));
            if (through.classClauseTo() != null) {
                items.add(alphabetItem(through.classClauseTo().literal(), "THRU"));
            }
        }
        result.add("items", items);
        return result;
    }

    private static String upperText(ParserRuleContext ctx) {
        return ctx == null ? "" : ctx.getText().toUpperCase();
    }

    private static boolean hasDecimalPointIsComma(ProgramUnit pu) {
        EnvironmentDivision env = pu.getEnvironmentDivision();
        return env != null && env.getSpecialNamesParagraph() != null
                && env.getSpecialNamesParagraph().getDecimalPointClause() != null;
    }

    /**
     * OBJECT-COMPUTER's PROGRAM COLLATING SEQUENCE IS alphabet-name (FOR
     * ALPHANUMERIC when written), as the format-1 ALPHABET clause it names.
     */
    private static void serializeProgramCollatingSequence(
            EnvironmentDivision env, SpecialNamesParagraph snp, JsonObject result) {
        ConfigurationSection config = env.getConfigurationSection();
        if (config == null || config.getObjectComputerParagraph() == null) return;
        CollatingSequenceClause clause =
                config.getObjectComputerParagraph().getCollatingSequenceClause();
        if (clause == null) return;
        String name = clause.getAlphaNumeric() != null
                ? clause.getAlphaNumeric()
                : clause.getAlphabetNames().get(0);
        for (AlphabetClause alphabet : snp.getAlphabetClauses()) {
            if (alphabet.getCtx() instanceof CobolParser.AlphabetClauseFormat1Context ctx
                    && ctx.alphabetName().getText().equalsIgnoreCase(name)) {
                result.add("program_collating_sequence", serializeAlphabet(ctx));
            }
        }
    }

    /**
     * A format-1 ALPHABET clause: its name and either a named character set
     * ({@code "kind"}: NATIVE, EBCDIC, ASCII, STANDARD-1, STANDARD-2, ALIAS for an
     * implementor-name) or, for the literal phrase, {@code "kind": "LITERALS"}
     * with the literals in source order, each tagged with what links it to the
     * literal before it (NONE, THRU or ALSO). The flat order is kept because the
     * grammar's grouping of ALSO operands is not the standard's: every ALSO takes
     * exactly one literal.
     */
    private static JsonObject serializeAlphabet(CobolParser.AlphabetClauseFormat1Context ctx) {
        JsonObject alphabet = new JsonObject();
        alphabet.addProperty("name", ctx.alphabetName().getText().toUpperCase());
        alphabet.addProperty("kind", alphabetKind(ctx));
        JsonArray items = new JsonArray();
        for (CobolParser.AlphabetLiteralsContext lits : ctx.alphabetLiterals()) {
            items.add(alphabetItem(lits.literal(), "NONE"));
            if (lits.alphabetThrough() != null) {
                items.add(alphabetItem(lits.alphabetThrough().literal(), "THRU"));
            }
            for (CobolParser.AlphabetAlsoContext also : lits.alphabetAlso()) {
                List<CobolParser.LiteralContext> operands = also.literal();
                items.add(alphabetItem(operands.get(0), "ALSO"));
                for (CobolParser.LiteralContext operand : operands.subList(1, operands.size())) {
                    items.add(alphabetItem(operand, "NONE"));
                }
            }
        }
        if (items.size() > 0) {
            alphabet.add("items", items);
        }
        return alphabet;
    }

    private static String alphabetKind(CobolParser.AlphabetClauseFormat1Context ctx) {
        if (ctx.EBCDIC() != null) return "EBCDIC";
        if (ctx.ASCII() != null) return "ASCII";
        if (ctx.STANDARD_1() != null) return "STANDARD-1";
        if (ctx.STANDARD_2() != null) return "STANDARD-2";
        if (ctx.NATIVE() != null) return "NATIVE";
        if (ctx.cobolWord() != null) return "ALIAS";
        return "LITERALS";
    }

    private static JsonObject alphabetItem(CobolParser.LiteralContext lit, String link) {
        JsonObject item = new JsonObject();
        item.addProperty("link", link);
        if (lit.figurativeConstant() != null) {
            item.addProperty("kind", "FIGURATIVE");
            item.addProperty("value", lit.figurativeConstant().getText().toUpperCase());
        } else if (lit.numericLiteral() != null) {
            item.addProperty("kind", "NUMERIC");
            item.addProperty("value", lit.numericLiteral().getText());
        } else {
            item.addProperty("kind", "NONNUMERIC");
            item.addProperty("value", nonnumericCharacters(lit.getText()));
        }
        return item;
    }

    /** A nonnumeric literal's characters: delimiters removed, doubled delimiters undone. */
    private static String nonnumericCharacters(String text) {
        String delimiter = text.substring(0, 1);
        return text.substring(1, text.length() - 1).replace(delimiter + delimiter, delimiter);
    }

    /** Literal text with COBOL quote delimiters stripped. */
    private static String literalText(io.proleap.cobol.asg.metamodel.Literal lit) {
        String text = (lit.getCtx() != null) ? lit.getCtx().getText() : lit.toString();
        return text.replaceAll("^['\"]|['\"]$", "");
    }

    /**
     * Extracts DATA DIVISION fields from Working-Storage, Linkage, Local-Storage,
     * and File sections.
     */
    private static void serializeDataDivision(ProgramUnit pu, JsonObject asg) {
        DataDivision dataDivision = pu.getDataDivision();
        if (dataDivision == null) {
            LOG.info("No DATA DIVISION found");
            return;
        }

        // Collects every EXEC SQL data-description entry found across the
        // sections below (e.g. a DECLARE CURSOR written in WORKING-STORAGE
        // rather than PROCEDURE DIVISION) into one top-level array, tagged
        // by which section it came from -- see DataFieldSerializer's
        // serializeExecSqlEntries. Never folded into data_fields/etc.:
        // sectioned_layout assigns storage offsets to everything in those
        // arrays, and an EXEC SQL entry has no storage (forge-qhi).
        JsonArray execSqlEntries = new JsonArray();

        WorkingStorageSection ws = dataDivision.getWorkingStorageSection();
        if (ws != null) {
            List<DataDescriptionEntry> rootEntries = ws.getRootDataDescriptionEntries();
            if (rootEntries != null && !rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("data_fields", fields);
                LOG.info("Serialized " + fields.size() + " working-storage fields");

                for (com.google.gson.JsonElement elem : DataFieldSerializer
                        .serializeExecSqlEntries(rootEntries, "WORKING-STORAGE")) {
                    execSqlEntries.add(elem);
                }
            }
        }

        LinkageSection ls = dataDivision.getLinkageSection();
        if (ls != null) {
            List<DataDescriptionEntry> rootEntries = ls.getRootDataDescriptionEntries();
            if (rootEntries != null && !rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("linkage_fields", fields);
                LOG.info("Serialized " + fields.size() + " linkage fields");

                for (com.google.gson.JsonElement elem : DataFieldSerializer
                        .serializeExecSqlEntries(rootEntries, "LINKAGE")) {
                    execSqlEntries.add(elem);
                }
            }
        }

        LocalStorageSection lss = dataDivision.getLocalStorageSection();
        if (lss != null) {
            List<DataDescriptionEntry> rootEntries = lss.getRootDataDescriptionEntries();
            if (rootEntries != null && !rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("local_storage_fields", fields);
                LOG.info("Serialized " + fields.size() + " local-storage fields");

                for (com.google.gson.JsonElement elem : DataFieldSerializer
                        .serializeExecSqlEntries(rootEntries, "LOCAL-STORAGE")) {
                    execSqlEntries.add(elem);
                }
            }
        }

        if (execSqlEntries.size() > 0) {
            asg.add("data_division_exec_sql", execSqlEntries);
            LOG.info("Serialized " + execSqlEntries.size() + " EXEC SQL data-division entries");
        }

        FileSection fileSection = dataDivision.getFileSection();
        if (fileSection != null) {
            // Flatten every FD's record entries into one list, tagging each
            // 01-level root entry with its FD (SELECT) name so the Python side
            // can map record names back to file names. Each FD's records share
            // one record area; the FDs' areas follow each other.
            JsonArray allFields = new JsonArray();
            int areaBase = 0;
            for (FileDescriptionEntry fd : fileSection.getFileDescriptionEntries()) {
                String fdName = fd.getName();
                List<DataDescriptionEntry> fdRoots =
                        new ArrayList<>(fd.getRootDataDescriptionEntries());
                JsonArray fdFields = DataFieldSerializer.serializeRecordArea(fdRoots, areaBase);
                areaBase += DataFieldSerializer.recordAreaLength(fdRoots);
                for (int i = 0; i < fdFields.size(); i++) {
                    fdFields.get(i).getAsJsonObject().addProperty("fd_name", fdName);
                }
                for (com.google.gson.JsonElement elem : fdFields) {
                    allFields.add(elem);
                }
            }
            if (allFields.size() > 0) {
                asg.add("file_fields", allFields);
                LOG.info("Serialized " + allFields.size() + " file-section fields");
            }
            JsonArray fileDescriptions = new JsonArray();
            for (FileDescriptionEntry fd : fileSection.getFileDescriptionEntries()) {
                fileDescriptions.add(FileDescriptionSerializer.serialize(fd));
            }
            if (fileDescriptions.size() > 0) {
                asg.add("file_descriptions", fileDescriptions);
            }
        }
    }

    /**
     * Extracts PROCEDURE DIVISION sections and paragraphs.
     *
     * <p>If sections exist, paragraphs are nested within sections.
     * Standalone paragraphs (not inside a section) go into the top-level
     * "paragraphs" array.
     */
    private static void serializeProcedureDivision(ProgramUnit pu, JsonObject asg) {
        ProcedureDivision pd = pu.getProcedureDivision();
        if (pd == null) {
            LOG.info("No PROCEDURE DIVISION found");
            return;
        }

        JsonArray using = serializeProcedureUsing(pd.getUsingClause());
        if (using.size() > 0) {
            asg.add("procedure_using", using);
        }

        Collection<Section> sections = pd.getSections();
        Collection<Paragraph> allParagraphs = pd.getParagraphs();
        Declaratives decl = pd.getDeclaratives();

        if (sections != null && !sections.isEmpty()) {
            JsonArray sectionsArray = serializeSections(sections);
            if (sectionsArray.size() > 0) {
                asg.add("sections", sectionsArray);
            }
        }

        // Standalone paragraphs: not inside a section AND not inside declaratives.
        List<Paragraph> standaloneParagraphs =
                new ArrayList<>(findStandaloneParagraphs(sections, allParagraphs));
        standaloneParagraphs.removeIf(p -> isInDeclaratives(p, decl));
        if (!standaloneParagraphs.isEmpty()) {
            JsonArray parasArray = serializeParagraphs(standaloneParagraphs);
            if (parasArray.size() > 0) {
                asg.add("paragraphs", parasArray);
            }
        }

        // DECLARATIVES sections (event-driven USE procedures).
        JsonArray declArray = serializeDeclaratives(pd, allParagraphs);
        if (declArray.size() > 0) {
            asg.add("declaratives", declArray);
        }

        // Division-level bare statements (not inside any paragraph or section)
        List<Statement> divStatements = pd.getStatements();
        if (divStatements != null && !divStatements.isEmpty()) {
            JsonArray stmts = StatementSerializer.serializeStatements(divStatements);
            if (stmts.size() > 0) {
                asg.add("statements", stmts);
                LOG.info("Serialized " + stmts.size() + " division-level bare statements");
            }
        }
    }

    /**
     * PROCEDURE DIVISION USING, one entry per parameter in the order listed: the
     * position each caller's CALL USING argument binds to.
     */
    private static JsonArray serializeProcedureUsing(UsingClause clause) {
        JsonArray params = new JsonArray();
        if (clause == null || clause.getUsingParameters() == null) {
            return params;
        }
        for (UsingParameter param : clause.getUsingParameters()) {
            if (param.getByReferencePhrase() != null) {
                for (ByReference br : param.getByReferencePhrase().getByReferences()) {
                    params.add(usingEntry(
                            StatementSerializer.extractCallName(br.getReferenceCall()),
                            "REFERENCE"));
                }
            }
            if (param.getByValuePhrase() != null) {
                for (ByValue bv : param.getByValuePhrase().getByValues()) {
                    params.add(usingEntry(
                            StatementSerializer.extractValueStmtText(bv.getValueValueStmt()),
                            "VALUE"));
                }
            }
        }
        return params;
    }

    private static JsonObject usingEntry(String name, String type) {
        JsonObject entry = new JsonObject();
        entry.addProperty("name", name);
        entry.addProperty("type", type);
        return entry;
    }

    /**
     * Serializes PROCEDURE DIVISION sections.
     */
    private static JsonArray serializeSections(Collection<Section> sections) {
        JsonArray arr = new JsonArray();
        for (Section section : sections) {
            JsonObject sectionObj = new JsonObject();
            sectionObj.addProperty("name", section.getName());
            StatementSerializer.addSpan(sectionObj, section.getCtx());

            Collection<Paragraph> paras = section.getParagraphs();
            if (paras != null && !paras.isEmpty()) {
                JsonArray parasArray = serializeParagraphs(new ArrayList<>(paras));
                if (parasArray.size() > 0) {
                    sectionObj.add("paragraphs", parasArray);
                }
            }

            // Section-level bare statements (not inside any paragraph)
            List<Statement> sectionStatements = section.getStatements();
            if (sectionStatements != null && !sectionStatements.isEmpty()) {
                JsonArray stmts = StatementSerializer.serializeStatements(new ArrayList<>(sectionStatements));
                if (stmts.size() > 0) {
                    sectionObj.add("statements", stmts);
                }
            }

            arr.add(sectionObj);
        }
        return arr;
    }

    /**
     * True if a paragraph's first source line falls within the DECLARATIVES block.
     */
    private static boolean isInDeclaratives(Paragraph p, Declaratives decl) {
        if (decl == null || p.getCtx() == null || decl.getCtx() == null) {
            return false;
        }
        int line = p.getCtx().getStart().getLine();
        int start = decl.getCtx().getStart().getLine();
        int stop = decl.getCtx().getStop().getLine();
        return line >= start && line <= stop;
    }

    /**
     * Serializes DECLARATIVES sections. Each Declarative contributes one
     * {name, paragraphs} entry shaped exactly like a regular section. Paragraphs
     * are bucketed from pd.getParagraphs() by source-line range, because ProLeap
     * lists declaratives paragraphs in the flat paragraph list, not under the
     * declarative object.
     */
    private static AfterOn.AfterOnType afterOnType(AfterOn afterOn) {
        if (afterOn.getAfterOnType() != null) {
            return afterOn.getAfterOnType();
        }
        CobolParser.UseAfterOnContext ctx = (CobolParser.UseAfterOnContext) afterOn.getCtx();
        return ctx.EXTEND() != null ? AfterOn.AfterOnType.EXTEND : null;
    }

    private static JsonArray serializeDeclaratives(
            ProcedureDivision pd, Collection<Paragraph> allParagraphs) {
        JsonArray arr = new JsonArray();
        Declaratives decl = pd.getDeclaratives();
        if (decl == null) {
            return arr;
        }
        for (Declarative d : decl.getDeclaratives()) {
            JsonObject secObj = new JsonObject();
            String name = ((CobolParser.ProcedureSectionHeaderContext)
                    d.getSectionHeader().getCtx()).sectionName().getText();
            secObj.addProperty("name", name);
            // d.getCtx() is the whole procedureDeclarative: it starts at the
            // "<name> SECTION." header, like a regular section's ctx does.
            StatementSerializer.addSpan(secObj, d.getCtx());

            UseStatement us = d.getUseStament();
            // USE FOR DEBUGGING is out of scope; only AFTER ERROR/EXCEPTION is serialized.
            if (us != null
                    && us.getUseDebugStatement() == null
                    && us.getUseAfterStatement() != null) {
                UseAfterStatement ua = us.getUseAfterStatement();
                AfterOn afterOn = ua.getAfterOn();
                AfterOn.AfterOnType t = afterOn == null ? null : afterOnType(afterOn);
                if (t != null) {
                    JsonObject useObj = new JsonObject();
                    useObj.addProperty("global", ua.isGlobal());
                    String target = switch (t) {
                        case FILE -> "FILE";
                        case INPUT -> "INPUT";
                        case OUTPUT -> "OUTPUT";
                        case INPUT_OUTPUT -> "I-O";
                        case EXTEND -> "EXTEND";
                    };
                    useObj.addProperty("target", target);
                    if (t == AfterOn.AfterOnType.FILE && afterOn.getFileCalls() != null) {
                        JsonArray files = new JsonArray();
                        for (Call fc : afterOn.getFileCalls()) {
                            files.add(StatementSerializer.extractCallName(fc));
                        }
                        useObj.add("files", files);
                    }
                    secObj.add("use", useObj);
                }
            }

            int start = d.getCtx().getStart().getLine();
            int stop = d.getCtx().getStop().getLine();
            List<Paragraph> declParas = new ArrayList<>();
            for (Paragraph p : allParagraphs) {
                if (p.getCtx() == null) {
                    continue;
                }
                int line = p.getCtx().getStart().getLine();
                if (line >= start && line <= stop) {
                    declParas.add(p);
                }
            }
            if (!declParas.isEmpty()) {
                JsonArray parasArray = serializeParagraphs(declParas);
                if (parasArray.size() > 0) {
                    secObj.add("paragraphs", parasArray);
                }
            }
            arr.add(secObj);
        }
        return arr;
    }

    /**
     * Serializes a list of paragraphs.
     */
    private static JsonArray serializeParagraphs(List<Paragraph> paragraphs) {
        JsonArray arr = new JsonArray();
        for (Paragraph para : paragraphs) {
            JsonObject paraObj = new JsonObject();
            paraObj.addProperty("name", para.getName());
            if (para.getCtx() != null) {
                paraObj.addProperty("line_start", para.getCtx().getStart().getLine());
                paraObj.addProperty("col_start",  para.getCtx().getStart().getCharPositionInLine());
                paraObj.addProperty("line_end",   para.getCtx().getStop().getLine());
                paraObj.addProperty("col_end",    para.getCtx().getStop().getCharPositionInLine());
            }

            if (para.getStatements() != null && !para.getStatements().isEmpty()) {
                StatementSerializer.serializeSentences(para.getStatements(), paraObj);
            }

            arr.add(paraObj);
        }
        return arr;
    }

    /**
     * Serializes FILE-CONTROL entries from the ENVIRONMENT DIVISION to a JSON array.
     * Each entry has: file_name, assign_to, organization, access_mode, record_key,
     * relative_key, file_status_var.
     */
    /** The reference a FILE-CONTROL clause that is absent carries: no name. */
    private static JsonObject unnamedRef() {
        JsonObject ref = new JsonObject();
        ref.addProperty("name", "");
        return ref;
    }

    private static JsonArray serializeFileControl(ProgramUnit pu) {
        JsonArray result = new JsonArray();
        try {
            EnvironmentDivision env = pu.getEnvironmentDivision();
            if (env == null) return result;
            InputOutputSection ios = env.getInputOutputSection();
            if (ios == null) return result;
            FileControlParagraph fcp = ios.getFileControlParagraph();
            if (fcp == null) return result;
            for (FileControlEntry fce : fcp.getFileControlEntries()) {
                JsonObject entry = new JsonObject();
                entry.addProperty("file_name", fce.getName() != null ? fce.getName().toUpperCase() : "");

                // ASSIGN TO
                if (fce.getAssignClause() != null && fce.getAssignClause().getToValueStmt() != null) {
                    io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt vs = fce.getAssignClause().getToValueStmt();
                    String assign = (vs.getCtx() != null) ? vs.getCtx().getText() : vs.toString();
                    // Strip surrounding quotes if present
                    assign = assign.replaceAll("^['\"]|['\"]$", "");
                    entry.addProperty("assign_to", assign);
                } else {
                    entry.addProperty("assign_to", "");
                }

                // ORGANIZATION
                if (fce.getOrganizationClause() != null && fce.getOrganizationClause().getMode() != null) {
                    entry.addProperty("organization", fce.getOrganizationClause().getMode().name());
                } else {
                    entry.addProperty("organization", "SEQUENTIAL");
                }

                // ACCESS MODE
                if (fce.getAccessModeClause() != null && fce.getAccessModeClause().getMode() != null) {
                    entry.addProperty("access_mode", fce.getAccessModeClause().getMode().name());
                } else {
                    entry.addProperty("access_mode", "SEQUENTIAL");
                }

                // RECORD KEY
                if (fce.getRecordKeyClause() != null && fce.getRecordKeyClause().getRecordKeyCall() != null) {
                    entry.add("record_key",
                            StatementSerializer.serializeRef(fce.getRecordKeyClause().getRecordKeyCall()));
                } else {
                    entry.add("record_key", unnamedRef());
                }

                // RELATIVE KEY
                if (fce.getRelativeKeyClause() != null && fce.getRelativeKeyClause().getRelativeKeyCall() != null) {
                    entry.add("relative_key",
                            StatementSerializer.serializeRef(fce.getRelativeKeyClause().getRelativeKeyCall()));
                } else {
                    entry.add("relative_key", unnamedRef());
                }

                // FILE STATUS
                if (fce.getFileStatusClause() != null && fce.getFileStatusClause().getDataCall() != null) {
                    entry.add("file_status_var",
                            StatementSerializer.serializeRef(fce.getFileStatusClause().getDataCall()));
                } else {
                    entry.add("file_status_var", unnamedRef());
                }

                result.add(entry);
            }
        } catch (Exception e) {
            LOG.warning("Could not serialize FILE-CONTROL: " + e.getMessage());
        }
        return result;
    }

    /**
     * Identifies paragraphs not nested inside any section.
     *
     * <p>ProLeap may list all paragraphs at the division level.
     * We filter out those that belong to a section.
     */
    private static List<Paragraph> findStandaloneParagraphs(
            Collection<Section> sections,
            Collection<Paragraph> allParagraphs) {

        if (allParagraphs == null || allParagraphs.isEmpty()) {
            return List.of();
        }

        if (sections == null || sections.isEmpty()) {
            return new ArrayList<>(allParagraphs);
        }

        // Collect paragraph names that belong to sections
        List<String> sectionParaNames = sections.stream()
                .filter(s -> s.getParagraphs() != null)
                .flatMap(s -> s.getParagraphs().stream())
                .map(Paragraph::getName)
                .toList();

        return allParagraphs.stream()
                .filter(p -> !sectionParaNames.contains(p.getName()))
                .toList();
    }
}
