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
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.junit.Assert.*;

/**
 * A paragraph that is only {@code GO TO.}: Cobol.g4 parses it as the paragraph's
 * {@code alteredGoTo}, which ProLeap's ASG keeps no statement for. It is serialized as
 * the paragraph's one GOTO statement of form "altered", the GO TO an ALTER supplies the
 * target of. (red-dragon-sl30.93)
 */
public class AlteredGoToSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void aGoToWithNoOperandIsTheParagraphsOneAlteredGoTo() throws Exception {
        JsonObject paragraph = paragraph("G-A");
        JsonArray statements = paragraph.getAsJsonArray("statements");
        assertEquals(1, statements.size());
        JsonObject goTo = statements.get(0).getAsJsonObject();
        assertEquals("GOTO", goTo.get("type").getAsString());
        assertEquals("altered", goTo.get("form").getAsString());
        assertEquals(8, goTo.get("line_start").getAsInt());
        assertEquals(0, paragraph.getAsJsonArray("sentence_ends").get(0).getAsInt());
        assertEquals(1, paragraph.getAsJsonArray("sentence_ends").size());
    }

    private JsonObject paragraph(String name) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/altered_goto.cbl");
        assertNotNull("Fixture not found", resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        JsonObject asg = AsgSerializer.serialize(program).getAsJsonArray("programs").get(0).getAsJsonObject();
        for (JsonElement p : asg.getAsJsonArray("paragraphs")) {
            if (name.equals(p.getAsJsonObject().get("name").getAsString())) {
                return p.getAsJsonObject();
            }
        }
        throw new AssertionError("paragraph not serialized: " + name);
    }
}
