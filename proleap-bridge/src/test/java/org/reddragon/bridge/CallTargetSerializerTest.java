package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;
import org.junit.BeforeClass;
import org.junit.Test;

import java.io.File;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.junit.Assert.*;

/**
 * CALL's callee: Cobol.g4:1241 is {@code CALL (identifier | literal)}, and the two
 * arms mean different things at run time. A literal names the program; an
 * identifier's contents do. Flattening the identifier arm to text — which is what
 * the serializer used to do, emitting "WS-PROG(1:8)" as a program name — loses both
 * the distinction and the subscript/ref-mod structure, so the frontend would call
 * the wrong program or none at all. (red-dragon-jgra)
 */
public class CallTargetSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void testLiteralCalleeStaysAPlainProgramName() throws Exception {
        JsonObject call = getCall(0);
        assertEquals("DSNTIAC", call.get("program").getAsString());
        assertFalse("a literal callee is not a runtime reference", call.has("program_ref"));
    }

    @Test
    public void testDataNameCalleeIsAStructuredReference() throws Exception {
        JsonObject call = getCall(1);
        assertFalse("an identifier callee is not a literal name", call.has("program"));
        JsonObject ref = call.getAsJsonObject("program_ref");
        assertEquals("WS-PROG", ref.get("name").getAsString());
    }

    @Test
    public void testSubscriptedCalleeKeepsItsSubscript() throws Exception {
        JsonObject ref = getCall(2).getAsJsonObject("program_ref");
        assertEquals("WS-PROG-E", ref.get("name").getAsString());
        JsonArray subs = ref.getAsJsonArray("subscripts");
        assertEquals(1, subs.size());
        assertEquals("WS-IDX", subs.get(0).getAsJsonObject().get("name").getAsString());
    }

    @Test
    public void testReferenceModifiedCalleeKeepsItsBounds() throws Exception {
        // CALL WS-PROG(1:8) — program names are 8 characters and the holding
        // field is usually wider, so this is the common real idiom. Dropping the
        // slice would call whatever the whole field spells.
        JsonObject ref = getCall(3).getAsJsonObject("program_ref");
        assertEquals("WS-PROG", ref.get("name").getAsString());
        assertFalse("the name must not glue the slice on",
                ref.get("name").getAsString().contains("("));
        assertEquals("1", ref.getAsJsonObject("ref_mod_start").get("value").getAsString());
        assertEquals("8", ref.getAsJsonObject("ref_mod_length").get("value").getAsString());
    }

    @Test
    public void testQualifiedCalleeKeepsLeafNameAndQualifier() throws Exception {
        // CALL WS-INNER OF WS-GRP used to come out as the glued "WS-INNEROFWS-GRP".
        JsonObject ref = getCall(4).getAsJsonObject("program_ref");
        assertEquals("WS-INNER", ref.get("name").getAsString());
        JsonArray qualifiers = ref.getAsJsonArray("qualifiers");
        assertEquals(1, qualifiers.size());
        assertEquals("WS-GRP", qualifiers.get(0).getAsString());
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private JsonObject getCall(int index) throws Exception {
        JsonObject asg = parseFixture("call_target.cbl");
        JsonObject para = findParagraph(asg.getAsJsonArray("paragraphs"), "MAIN-PARA");
        assertNotNull("MAIN-PARA must exist", para);
        List<JsonObject> calls = new ArrayList<>();
        for (JsonElement e : para.getAsJsonArray("statements")) {
            JsonObject s = e.getAsJsonObject();
            if ("CALL".equals(s.get("type").getAsString())) {
                calls.add(s);
            }
        }
        assertTrue("CALL #" + index + " must exist", calls.size() > index);
        return calls.get(index);
    }

    private JsonObject parseFixture(String filename) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/" + filename);
        assertNotNull("Fixture not found: " + filename, resource);
        File file = new File(resource.toURI());
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(file, CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program);
    }

    private JsonObject findParagraph(JsonArray paragraphs, String name) {
        for (JsonElement elem : paragraphs) {
            JsonObject para = elem.getAsJsonObject();
            if (name.equalsIgnoreCase(para.get("name").getAsString())) {
                return para;
            }
        }
        return null;
    }
}
