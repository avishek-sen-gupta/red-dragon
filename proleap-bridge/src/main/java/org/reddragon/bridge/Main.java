package org.reddragon.bridge;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.file.Files;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * CLI entry point for the ProLeap COBOL Bridge.
 *
 * <p>Usage:
 * <ul>
 *   <li>No args: reads COBOL source from stdin</li>
 *   <li>One arg: reads from file path</li>
 *   <li>{@code -format FIXED|FREE|TANDEM}: sets source format (default FIXED)</li>
 * </ul>
 *
 * <p>Writes JSON ASG to stdout, matching the RedDragon {@code CobolASG} contract.
 */
public final class Main {

    private static final Logger LOG = Logger.getLogger(Main.class.getName());

    private Main() {
        // prevent instantiation
    }

    public static void main(String[] args) throws Exception {
        suppressProLeapLogging();

        CobolSourceFormatEnum format = CobolSourceFormatEnum.FIXED;
        String filePath = "";

        for (int i = 0; i < args.length; i++) {
            if ("-format".equals(args[i]) && i + 1 < args.length) {
                format = parseFormat(args[i + 1]);
                i++;
            } else {
                filePath = args[i];
            }
        }

        File cobolFile = resolveInputFile(filePath);
        LOG.info("Parsing COBOL file: " + cobolFile.getAbsolutePath() + " (format=" + format + ")");

        // ProLeap prints debug info directly to stdout; capture and discard it
        PrintStream originalOut = System.out;
        System.setOut(new PrintStream(new ByteArrayOutputStream()));
        Program program;
        try {
            program = new CobolParserRunnerImpl().analyzeFile(cobolFile, format);
        } finally {
            System.setOut(originalOut);
        }

        JsonObject asg = AsgSerializer.serialize(program);
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        System.out.println(gson.toJson(asg));

        if (filePath.isEmpty()) {
            cobolFile.delete();
        }
    }

    private static File resolveInputFile(String filePath) throws IOException {
        if (!filePath.isEmpty()) {
            File f = new File(filePath);
            if (!f.exists()) {
                throw new IOException("File not found: " + filePath);
            }
            return f;
        }

        LOG.info("Reading COBOL source from stdin...");
        File tempFile = Files.createTempFile("cobol-bridge-", ".cbl").toFile();
        tempFile.deleteOnExit();
        byte[] stdinBytes = System.in.readAllBytes();
        Files.write(tempFile.toPath(), stdinBytes);
        return tempFile;
    }

    private static CobolSourceFormatEnum parseFormat(String formatStr) {
        return switch (formatStr.toUpperCase()) {
            case "VARIABLE" -> CobolSourceFormatEnum.VARIABLE;
            case "TANDEM" -> CobolSourceFormatEnum.TANDEM;
            default -> CobolSourceFormatEnum.FIXED;
        };
    }

    private static void suppressProLeapLogging() {
        Logger.getLogger("io.proleap").setLevel(Level.OFF);
        Logger.getLogger("org.antlr").setLevel(Level.OFF);
    }
}
