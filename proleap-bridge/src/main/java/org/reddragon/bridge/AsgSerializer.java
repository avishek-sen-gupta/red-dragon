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
import io.proleap.cobol.asg.metamodel.environment.inputoutput.InputOutputSection;
import io.proleap.cobol.asg.metamodel.environment.inputoutput.filecontrol.FileControlEntry;
import io.proleap.cobol.asg.metamodel.environment.inputoutput.filecontrol.FileControlParagraph;
import io.proleap.cobol.asg.metamodel.identification.IdentificationDivision;
import io.proleap.cobol.asg.metamodel.procedure.Paragraph;
import io.proleap.cobol.asg.metamodel.procedure.ProcedureDivision;
import io.proleap.cobol.asg.metamodel.procedure.Section;
import io.proleap.cobol.asg.metamodel.procedure.Statement;

import java.util.ArrayList;
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
 *   "local_storage_fields": [...], // LOCAL-STORAGE SECTION (optional)
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

        serializeDataDivision(pu, asg);
        serializeProcedureDivision(pu, asg);
        asg.add("file_control", serializeFileControl(pu));

        return asg;
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

        WorkingStorageSection ws = dataDivision.getWorkingStorageSection();
        if (ws != null) {
            List<DataDescriptionEntry> rootEntries = ws.getRootDataDescriptionEntries();
            if (rootEntries != null && !rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("data_fields", fields);
                LOG.info("Serialized " + fields.size() + " working-storage fields");
            }
        }

        LinkageSection ls = dataDivision.getLinkageSection();
        if (ls != null) {
            List<DataDescriptionEntry> rootEntries = ls.getRootDataDescriptionEntries();
            if (rootEntries != null && !rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("linkage_fields", fields);
                LOG.info("Serialized " + fields.size() + " linkage fields");
            }
        }

        LocalStorageSection lss = dataDivision.getLocalStorageSection();
        if (lss != null) {
            List<DataDescriptionEntry> rootEntries = lss.getRootDataDescriptionEntries();
            if (rootEntries != null && !rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("local_storage_fields", fields);
                LOG.info("Serialized " + fields.size() + " local-storage fields");
            }
        }

        FileSection fileSection = dataDivision.getFileSection();
        if (fileSection != null) {
            // Flatten every FD's record entries into one list. For a single FD
            // (the common case) byte offsets are correct; multiple FDs would get
            // sequential offsets rather than each starting at 0 — acceptable for
            // this layout-only slice (no file buffering yet).
            List<DataDescriptionEntry> rootEntries = new ArrayList<>();
            for (FileDescriptionEntry fd : fileSection.getFileDescriptionEntries()) {
                rootEntries.addAll(fd.getRootDataDescriptionEntries());
            }
            if (!rootEntries.isEmpty()) {
                JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
                asg.add("file_fields", fields);
                LOG.info("Serialized " + fields.size() + " file-section fields");
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

        Collection<Section> sections = pd.getSections();
        Collection<Paragraph> allParagraphs = pd.getParagraphs();

        if (sections != null && !sections.isEmpty()) {
            JsonArray sectionsArray = serializeSections(sections);
            if (sectionsArray.size() > 0) {
                asg.add("sections", sectionsArray);
            }
        }

        // Standalone paragraphs (those not inside a section)
        List<Paragraph> standaloneParagraphs = findStandaloneParagraphs(sections, allParagraphs);
        if (!standaloneParagraphs.isEmpty()) {
            JsonArray parasArray = serializeParagraphs(standaloneParagraphs);
            if (parasArray.size() > 0) {
                asg.add("paragraphs", parasArray);
            }
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
     * Serializes PROCEDURE DIVISION sections.
     */
    private static JsonArray serializeSections(Collection<Section> sections) {
        JsonArray arr = new JsonArray();
        for (Section section : sections) {
            JsonObject sectionObj = new JsonObject();
            sectionObj.addProperty("name", section.getName());

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
     * Serializes a list of paragraphs.
     */
    private static JsonArray serializeParagraphs(List<Paragraph> paragraphs) {
        JsonArray arr = new JsonArray();
        for (Paragraph para : paragraphs) {
            JsonObject paraObj = new JsonObject();
            paraObj.addProperty("name", para.getName());

            if (para.getStatements() != null && !para.getStatements().isEmpty()) {
                JsonArray stmts = StatementSerializer.serializeStatements(para.getStatements());
                if (stmts.size() > 0) {
                    paraObj.add("statements", stmts);
                }
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
                    io.proleap.cobol.asg.metamodel.call.Call rkCall = fce.getRecordKeyClause().getRecordKeyCall();
                    String rkName = rkCall.getName() != null ? rkCall.getName() : rkCall.toString();
                    entry.addProperty("record_key", rkName.toUpperCase());
                } else {
                    entry.addProperty("record_key", "");
                }

                // RELATIVE KEY
                if (fce.getRelativeKeyClause() != null && fce.getRelativeKeyClause().getRelativeKeyCall() != null) {
                    io.proleap.cobol.asg.metamodel.call.Call relCall = fce.getRelativeKeyClause().getRelativeKeyCall();
                    String relName = relCall.getName() != null ? relCall.getName() : relCall.toString();
                    entry.addProperty("relative_key", relName.toUpperCase());
                } else {
                    entry.addProperty("relative_key", "");
                }

                // FILE STATUS
                if (fce.getFileStatusClause() != null && fce.getFileStatusClause().getDataCall() != null) {
                    io.proleap.cobol.asg.metamodel.call.Call fsCall = fce.getFileStatusClause().getDataCall();
                    String fsName = fsCall.getName() != null ? fsCall.getName() : fsCall.toString();
                    entry.addProperty("file_status_var", fsName.toUpperCase());
                } else {
                    entry.addProperty("file_status_var", "");
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
