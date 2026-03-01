package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.CompilationUnit;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.metamodel.ProgramUnit;
import io.proleap.cobol.asg.metamodel.data.DataDivision;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.workingstorage.WorkingStorageSection;
import io.proleap.cobol.asg.metamodel.procedure.Paragraph;
import io.proleap.cobol.asg.metamodel.procedure.ProcedureDivision;
import io.proleap.cobol.asg.metamodel.procedure.Section;

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
 *   "data_fields": [...],
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

        serializeDataDivision(pu, asg);
        serializeProcedureDivision(pu, asg);

        return asg;
    }

    /**
     * Extracts DATA DIVISION fields from Working-Storage Section.
     */
    private static void serializeDataDivision(ProgramUnit pu, JsonObject asg) {
        DataDivision dataDivision = pu.getDataDivision();
        if (dataDivision == null) {
            LOG.info("No DATA DIVISION found");
            return;
        }

        WorkingStorageSection ws = dataDivision.getWorkingStorageSection();
        if (ws == null) {
            LOG.info("No WORKING-STORAGE SECTION found");
            return;
        }

        List<DataDescriptionEntry> rootEntries = ws.getRootDataDescriptionEntries();
        if (rootEntries != null && !rootEntries.isEmpty()) {
            JsonArray fields = DataFieldSerializer.serializeEntries(rootEntries);
            asg.add("data_fields", fields);
            LOG.info("Serialized " + fields.size() + " data fields");
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
