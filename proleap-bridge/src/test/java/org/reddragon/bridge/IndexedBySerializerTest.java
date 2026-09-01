package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;
import org.junit.BeforeClass;
import org.junit.Test;

import java.io.File;
import java.net.URL;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.junit.Assert.*;

/** OCCURS ... INDEXED BY names must reach the JSON; they are the only declaration
 *  an index item ever gets, so if they are dropped here nothing downstream can
 *  allocate the item and every subscript using it is unresolvable. */
public class IndexedBySerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void indexNamesAreEmittedOnTheOccursGroup() throws Exception {
        JsonObject group = findField(serializeFixture("indexed_by.cbl"), "TBL-ROW");
        assertNotNull("TBL-ROW not found in serialized ASG", group);
        assertTrue("no indexed_by key emitted", group.has("indexed_by"));
        JsonArray names = group.getAsJsonArray("indexed_by");
        assertEquals(2, names.size());
        assertEquals("TBL-IX", names.get(0).getAsString());
        assertEquals("TBL-JX", names.get(1).getAsString());
    }

    @Test
    public void aTableWithoutIndexedByEmitsNoKey() throws Exception {
        JsonObject group = findField(serializeFixture("xml_generate.cbl"), "SOME-RECORD");
        if (group != null) {
            assertFalse(group.has("indexed_by"));
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private JsonObject serializeFixture(String fixtureName) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/" + fixtureName);
        assertNotNull("Fixture not found", resource);

        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program);
    }

    /** Depth-first search over data_fields (and their children) for a field by name. */
    private JsonObject findField(JsonObject asg, String name) {
        JsonArray dataFields = asg.getAsJsonArray("data_fields");
        if (dataFields == null) {
            return null;
        }
        return findField(dataFields, name);
    }

    private JsonObject findField(JsonArray fields, String name) {
        for (int i = 0; i < fields.size(); i++) {
            JsonObject field = fields.get(i).getAsJsonObject();
            if (field.has("name") && name.equals(field.get("name").getAsString())) {
                return field;
            }
            if (field.has("children")) {
                JsonObject found = findField(field.getAsJsonArray("children"), name);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
