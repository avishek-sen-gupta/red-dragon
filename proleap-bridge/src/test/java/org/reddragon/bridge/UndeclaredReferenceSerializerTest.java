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

/** A name the program never declares, as when its copybook is missing, keeps the
 *  subscripts written on it: ProLeap resolves no TableCall for it, so the subscripts
 *  are read from the parse tree as written. */
public class UndeclaredReferenceSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void anUndeclaredNameKeepsItsSubscriptsAsWritten() throws Exception {
        List<JsonObject> moves = moves();

        assertEquals("[{\"kind\":\"lit\",\"value\":\"2\",\"numeric\":true}]",
                subscripts(moves.get(0), 1).toString());
        assertEquals("WS-IDX",
                subscripts(moves.get(1), 1).get(0).getAsJsonObject().get("name").getAsString());
        assertEquals(2, subscripts(moves.get(2), 1).size());
        assertEquals("[{\"kind\":\"lit\",\"value\":\"3\",\"numeric\":true}]",
                subscripts(moves.get(3), 0).toString());
        assertEquals("CPY-ROW",
                moves.get(3).getAsJsonArray("operands").get(0).getAsJsonObject()
                        .get("name").getAsString());
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private JsonArray subscripts(JsonObject move, int operand) {
        JsonObject ref = move.getAsJsonArray("operands").get(operand).getAsJsonObject();
        assertTrue("no subscripts on " + ref, ref.has("subscripts"));
        return ref.getAsJsonArray("subscripts");
    }

    private List<JsonObject> moves() throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/undeclared_refs.cbl");
        assertNotNull(resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        JsonObject asg = AsgSerializer.serialize(program).getAsJsonArray("programs")
                .get(0).getAsJsonObject();
        List<JsonObject> found = new ArrayList<>();
        for (JsonElement p : asg.getAsJsonArray("paragraphs")) {
            for (JsonElement s : p.getAsJsonObject().getAsJsonArray("statements")) {
                if ("MOVE".equals(s.getAsJsonObject().get("type").getAsString())) {
                    found.add(s.getAsJsonObject());
                }
            }
        }
        assertEquals(4, found.size());
        return found;
    }
}
