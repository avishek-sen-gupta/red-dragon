package org.reddragon.bridge;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.params.CobolParserParams;
import io.proleap.cobol.asg.params.impl.CobolParserParamsImpl;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
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
 *   <li>{@code -copybook-dir <dir>}: copybook search directory (repeatable)</li>
 *   <li>{@code -copybook-ext <ext>}: copybook filename extension (repeatable;
 *       defaults to {@link #DEFAULT_COPYBOOK_EXTENSIONS} when not given)</li>
 * </ul>
 *
 * <p>Writes JSON ASG to stdout, matching the RedDragon {@code CobolASG} contract.
 */
public final class Main {

    /**
     * The extensions searched when the caller names none. ProLeap resolves a
     * COPY by name + extension, so this list is corpus shape rather than a
     * constant: a corpus whose members all carry one unconventional extension
     * resolves nothing under it and must pass its own.
     */
    static final List<String> DEFAULT_COPYBOOK_EXTENSIONS =
        Arrays.asList("", "cpy", "CPY", "cob", "cbl", "copy", "COPY");

    private static final Logger LOG = Logger.getLogger(Main.class.getName());

    private Main() {
        // prevent instantiation
    }

    /**
     * The codec for every byte crossing this bridge: source in, copybooks off
     * disk, JSON out.
     *
     * <p>Fixed-format members are 8-bit text, not UTF-8, which is the same
     * conclusion RedDragon's own {@code decode_source} reaches on the Python
     * side. ISO-8859-1 is the byte-identity codec: defined for all 256 byte
     * values, so it never raises and never loses a character, and one byte stays
     * one character so column positions and PIC lengths are unaffected.
     *
     * <p>It matters most for copybooks, because those are the one input the
     * Python side never decodes -- ProLeap opens them itself, and under strict
     * UTF-8 a comment banner's box-drawing byte raises MalformedInputException.
     * ProLeap catches that IOException and logs it through a logger with no
     * provider bound, so the COPY expands to nothing and the parse *succeeds*
     * with the whole record absent. The only symptom is a field-not-found error
     * naming a copybook that is present and complete.
     */
    static final Charset SOURCE_CHARSET = StandardCharsets.ISO_8859_1;

    public static void main(String[] args) throws Exception {
        suppressProLeapLogging();
        // Byte-identity on the way out too, so a high byte in a VALUE literal
        // survives the round trip regardless of the JVM's default charset.
        System.setOut(
            new PrintStream(new FileOutputStream(FileDescriptor.out), true, SOURCE_CHARSET));

        CobolSourceFormatEnum format = CobolSourceFormatEnum.FIXED;
        String filePath = "";
        List<File> copyBookDirs = new ArrayList<>();

        for (int i = 0; i < args.length; i++) {
            if ("-format".equals(args[i]) && i + 1 < args.length) {
                format = parseFormat(args[i + 1]);
                i++;
            } else if ("-copybook-dir".equals(args[i]) && i + 1 < args.length) {
                copyBookDirs.add(new File(args[i + 1]));
                i++;
            } else if ("-copybook-ext".equals(args[i]) && i + 1 < args.length) {
                i++;  // value consumed by copyBookExtensions(args)
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
            CobolParserParams params = new CobolParserParamsImpl();
            params.setFormat(format);
            params.setCharset(SOURCE_CHARSET);
            params.setCopyBookExtensions(copyBookExtensions(args));
            if (!copyBookDirs.isEmpty()) {
                params.setCopyBookDirectories(copyBookDirs);
            }
            program = new CobolParserRunnerImpl().analyzeFile(cobolFile, params);
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

    /**
     * Every {@code -copybook-ext} value, in the order given, or
     * {@link #DEFAULT_COPYBOOK_EXTENSIONS} when the flag is absent. Never
     * empty: an empty list would make ProLeap search nothing.
     */
    static List<String> copyBookExtensions(String[] args) {
        List<String> extensions = new ArrayList<>();
        for (int i = 0; i < args.length - 1; i++) {
            if ("-copybook-ext".equals(args[i])) {
                extensions.add(args[i + 1]);
                i++;
            }
        }
        return extensions.isEmpty() ? DEFAULT_COPYBOOK_EXTENSIONS : extensions;
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
