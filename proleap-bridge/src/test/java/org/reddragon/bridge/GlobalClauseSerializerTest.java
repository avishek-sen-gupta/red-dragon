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

/** The GLOBAL clause of a data description entry and of a file description entry reaches the JSON. */
public class GlobalClauseSerializerTest {

    @BeforeClass
    public static void suppressLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }

    @Test
    public void globalRecordsAndFilesAreMarkedAndOthersAreNot() throws Exception {
        JsonObject asg = serializeFixture("global_items.cbl");
        JsonArray data = asg.getAsJsonArray("data_fields");
        assertTrue(named(data, "SHARED-DATA").get("global").getAsBoolean());
        assertFalse(named(data, "OWN-DATA").has("global"));
        assertFalse(named(named(data, "SHARED-DATA").getAsJsonArray("children"), "SHARED-PART")
                .has("global"));
        JsonArray fds = asg.getAsJsonArray("file_descriptions");
        assertTrue(byFd(fds, "SHARED-FILE").get("global").getAsBoolean());
        assertFalse(byFd(fds, "OWN-FILE").get("global").getAsBoolean());
    }

    private JsonObject serializeFixture(String fixtureName) throws Exception {
        URL resource = getClass().getClassLoader().getResource("fixtures/" + fixtureName);
        assertNotNull("Fixture not found", resource);
        Program program = new CobolParserRunnerImpl()
                .analyzeFile(new File(resource.toURI()), CobolSourceFormatEnum.FIXED);
        return AsgSerializer.serialize(program).getAsJsonArray("programs").get(0).getAsJsonObject();
    }

    private JsonObject named(JsonArray fields, String name) {
        for (int i = 0; i < fields.size(); i++) {
            JsonObject field = fields.get(i).getAsJsonObject();
            if (name.equals(field.get("name").getAsString())) {
                return field;
            }
        }
        throw new AssertionError(name + " not serialized");
    }

    private JsonObject byFd(JsonArray fds, String name) {
        for (int i = 0; i < fds.size(); i++) {
            JsonObject fd = fds.get(i).getAsJsonObject();
            if (name.equals(fd.get("fd_name").getAsString())) {
                return fd;
            }
        }
        throw new AssertionError(name + " not serialized");
    }
}
