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

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

/**
 * A source holding programs one after another (batch) and programs contained in
 * others (nested, closed by END PROGRAM) serializes as the compilation unit: its
 * top-level programs, each with its PROGRAM-ID attribute, its own divisions and the
 * programs it directly contains. (red-dragon-ljku.1)
 */
public class ProgramUnitTreeSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void testCompilationUnitIsTheTreeOfPrograms() throws Exception {
        JsonArray topLevel = parseFixture("program_units.cbl").getAsJsonArray("programs");
        JsonObject outer = topLevel.get(0).getAsJsonObject();
        JsonObject middle = outer.getAsJsonArray("programs").get(0).getAsJsonObject();
        JsonObject inner = middle.getAsJsonArray("programs").get(0).getAsJsonObject();
        JsonObject sibling = outer.getAsJsonArray("programs").get(1).getAsJsonObject();
        JsonObject batched = topLevel.get(1).getAsJsonObject();

        assertEquals(List.of("OUTER", "BATCHED"), ids(topLevel));
        assertEquals(List.of("MIDDLE", "SIBLING"), ids(outer.getAsJsonArray("programs")));
        assertEquals(List.of("INNER"), ids(middle.getAsJsonArray("programs")));
        assertEquals(List.of(), ids(inner.getAsJsonArray("programs")));
        assertEquals(List.of(), ids(sibling.getAsJsonArray("programs")));
        assertEquals(List.of(), ids(batched.getAsJsonArray("programs")));

        assertEquals(List.of("", "COMMON", "INITIAL", "", ""),
                List.of(attribute(outer), attribute(middle), attribute(inner),
                        attribute(sibling), attribute(batched)));

        assertEquals(List.of("OUTER-PARA"), paragraphNames(outer));
        assertEquals(List.of("MIDDLE-PARA"), paragraphNames(middle));
        assertEquals(List.of("INNER-PARA"), paragraphNames(inner));
        assertEquals(List.of("SIBLING-PARA"), paragraphNames(sibling));
        assertEquals(List.of("BATCHED-PARA"), paragraphNames(batched));
        assertEquals(List.of("WS-OUTER"), fieldNames(outer));
        assertEquals(List.of("WS-MIDDLE"), fieldNames(middle));
    }

    private static List<String> ids(JsonArray programs) {
        List<String> result = new ArrayList<>();
        for (JsonElement program : programs) {
            result.add(program.getAsJsonObject().get("program_id").getAsString());
        }
        return result;
    }

    private static String attribute(JsonObject program) {
        return program.get("attribute").getAsString();
    }

    private static List<String> paragraphNames(JsonObject program) {
        List<String> result = new ArrayList<>();
        for (JsonElement paragraph : program.getAsJsonArray("paragraphs")) {
            result.add(paragraph.getAsJsonObject().get("name").getAsString());
        }
        return result;
    }

    private static List<String> fieldNames(JsonObject program) {
        List<String> result = new ArrayList<>();
        for (JsonElement field : program.getAsJsonArray("data_fields")) {
            result.add(field.getAsJsonObject().get("name").getAsString());
        }
        return result;
    }

    private JsonObject parseFixture(String filename) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/" + filename);
        assertNotNull("Fixture not found: " + filename, resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program);
    }
}
