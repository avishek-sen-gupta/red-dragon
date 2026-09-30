package org.reddragon.bridge;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * Command-line parsing: copybook extension resolution, and the expand-only mode.
 *
 * <p>ProLeap resolves a COPY by name + extension, so a corpus whose members
 * all carry one unconventional extension (one production corpus is entirely
 * .txt) resolves nothing under the built-in list. Callers pass the corpus's
 * own extensions; omitting the flag keeps the historical default.
 */
public class MainTest {

    @Test
    public void noFlagYieldsTheDefaultList() {
        assertEquals(
            Arrays.asList("", "cpy", "CPY", "cob", "cbl", "copy", "COPY"),
            Main.copyBookExtensions(new String[] {}));
    }

    @Test
    public void repeatedFlagsYieldEachExtensionInOrder() {
        String[] args = {"-copybook-ext", "cpy", "-copybook-ext", "txt"};

        assertEquals(Arrays.asList("cpy", "txt"), Main.copyBookExtensions(args));
    }

    @Test
    public void extensionsAreReadAlongsideOtherFlags() {
        String[] args = {
            "-copybook-dir", "sym", "-copybook-ext", "txt", "-format", "FIXED"
        };

        assertEquals(Arrays.asList("txt"), Main.copyBookExtensions(args));
    }

    @Test
    public void aTrailingFlagWithNoValueIsIgnored() {
        List<String> extensions = Main.copyBookExtensions(new String[] {"-copybook-ext"});

        assertEquals(
            Arrays.asList("", "cpy", "CPY", "cob", "cbl", "copy", "COPY"), extensions);
    }

    @Test
    public void withoutTheFlagTheBridgeEmitsAnAsg() {
        String[] args = {"-copybook-dir", "sym", "-format", "FIXED"};

        assertFalse(Main.expandOnly(args));
    }

    @Test
    public void theExpandOnlyFlagIsReadAlongsideOtherFlags() {
        String[] args = {"-copybook-dir", "sym", "-expand-only", "-copybook-ext", "txt"};

        assertTrue(Main.expandOnly(args));
    }
}
