package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.CobolParser;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryCondition;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryExecSql;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryGroup;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryRename;
import io.proleap.cobol.asg.metamodel.data.datadescription.BlankWhenZeroClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.Index;
import io.proleap.cobol.asg.metamodel.data.datadescription.OccursClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.OccursIndexed;
import io.proleap.cobol.asg.metamodel.data.datadescription.JustifiedClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.SignClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.SynchronizedClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.ValueInterval;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Logger;

/**
 * Serializes DATA DIVISION entries to JSON matching the CobolField contract.
 *
 * <p>Computes byte offsets using a running accumulator, mirroring the Python
 * {@code data_layout.py} offset logic. ProLeap does not compute offsets natively.
 */
public final class DataFieldSerializer {

    private static final Logger LOG = Logger.getLogger(DataFieldSerializer.class.getName());


    /** Bytes a USAGE POINTER item occupies: 4 under LP(32), 8 under LP(64). */
    private static int pointerSize = 4;

    /** Bytes a USAGE INDEX data item occupies: a fullword (IBM Enterprise COBOL LR, USAGE INDEX). */
    private static final int INDEX_ITEM_SIZE = 4;

    /** Bytes a COMP-1 item occupies: short floating point (IBM Enterprise COBOL LR, USAGE COMP-1). */
    private static final int COMP_1_SIZE = 4;

    /** Bytes a COMP-2 item occupies: long floating point (IBM Enterprise COBOL LR, USAGE COMP-2). */
    private static final int COMP_2_SIZE = 8;

    /** Running counter for disambiguating FILLER fields within a serialization session. */
    private int fillerCount = 0;

    private DataFieldSerializer() {
    }

    /** Sets the USAGE POINTER size for this run, from the -pointer-size option. */
    public static void setPointerSize(int bytes) {
        pointerSize = bytes;
    }

    /**
     * Serializes a list of top-level data entries (e.g. Working-Storage root entries).
     *
     * @param entries top-level DataDescriptionEntry list
     * @return JSON array of CobolField objects
     */
    public static JsonArray serializeEntries(List<DataDescriptionEntry> entries) {
        DataFieldSerializer instance = new DataFieldSerializer();
        JsonArray fields = new JsonArray();
        int runningOffset = 0;
        int areaStart = 0;

        for (DataDescriptionEntry entry : entries) {
            if (entry instanceof DataDescriptionEntryGroup group) {
                JsonObject field = instance.serializeGroup(group, runningOffset);
                fields.add(field);

                if (group.getRedefinesClause() == null) {
                    areaStart = runningOffset;
                    runningOffset += computeByteLength(group);
                } else {
                    runningOffset = Math.max(runningOffset, areaStart + computeByteLength(group));
                }
            } else if (entry instanceof DataDescriptionEntryRename rename) {
                JsonObject field = instance.serializeRename(rename);
                fields.add(field);
                // RENAMES does not allocate storage — no offset increment
            } else if (entry instanceof DataDescriptionEntryExecSql) {
                // Deliberately not serialized here: it has no storage and does
                // not belong in data_fields. Collected separately by
                // serializeExecSqlEntries (forge-qhi) -- see AsgSerializer's
                // "data_division_exec_sql" key. Named explicitly (not folded
                // into the else below) so it is never mistaken for the
                // unhandled-type case that else logs.
            } else {
                // Anything else is a ProLeap entry kind this serializer does
                // not yet know about. This is the exact trap forge-qhi found:
                // EXEC_SQL fell off the end of this chain silently -- no
                // error, no JSON node -- for years. Log loudly instead of
                // repeating that history for the next new kind.
                LOG.warning("Unhandled DataDescriptionEntry subtype: "
                        + entry.getClass().getName() + " -- dropped from data_fields");
            }
        }
        return fields;
    }

    /**
     * Serializes the records of one FD. Every 01 under an FD describes the same
     * record area (an implicit redefinition), so each starts at {@code base}.
     */
    public static JsonArray serializeRecordArea(List<DataDescriptionEntry> records, int base) {
        DataFieldSerializer instance = new DataFieldSerializer();
        JsonArray fields = new JsonArray();
        for (DataDescriptionEntry entry : records) {
            if (entry instanceof DataDescriptionEntryGroup group) {
                fields.add(instance.serializeGroup(group, base));
            } else if (entry instanceof DataDescriptionEntryRename rename) {
                fields.add(instance.serializeRename(rename));
            } else if (!(entry instanceof DataDescriptionEntryExecSql)) {
                LOG.warning("Unhandled DataDescriptionEntry subtype: "
                        + entry.getClass().getName() + " -- dropped from file_fields");
            }
        }
        return fields;
    }

    /** Bytes an FD's record area occupies: the length of its largest record. */
    public static int recordAreaLength(List<DataDescriptionEntry> records) {
        return records.stream()
                .filter(e -> e instanceof DataDescriptionEntryGroup)
                .mapToInt(e -> computeByteLength((DataDescriptionEntryGroup) e))
                .max()
                .orElse(0);
    }

    /**
     * Recursively collects every EXEC SQL data-description entry (e.g. a
     * DECLARE CURSOR written in WORKING-STORAGE rather than PROCEDURE
     * DIVISION) found anywhere under {@code entries}, including nested
     * inside group children. ProLeap already builds this node and populates
     * its text via {@link DataDescriptionEntryExecSql#getExecSqlText()};
     * {@link #serializeEntries} silently drops it because it carries no
     * storage. Each is tagged with which DATA DIVISION section it came from,
     * so the Python side can tell a WORKING-STORAGE declare from a LINKAGE
     * one without re-deriving that from source spans.
     *
     * @param entries root or child DataDescriptionEntry list to search
     * @param section the DATA DIVISION section name this list came from
     *                (e.g. "WORKING-STORAGE", "LINKAGE", "LOCAL-STORAGE")
     * @return JSON array of {section, exec_sql_text, line_start, col_start,
     *         line_end, col_end} objects, in source order
     */
    public static JsonArray serializeExecSqlEntries(List<DataDescriptionEntry> entries, String section) {
        JsonArray out = new JsonArray();
        collectExecSqlEntries(entries, section, out);
        return out;
    }

    private static void collectExecSqlEntries(
            List<DataDescriptionEntry> entries, String section, JsonArray out) {
        if (entries == null) {
            return;
        }
        for (DataDescriptionEntry entry : entries) {
            if (entry instanceof DataDescriptionEntryExecSql execSql) {
                String text = execSql.getExecSqlText();
                if (text == null) {
                    // A null here would reach Python as None and crash
                    // parse_exec_sql at compile time -- skip and log loudly
                    // rather than emit a node the consumer cannot use.
                    LOG.warning("DataDescriptionEntryExecSql with null exec_sql_text -- skipped");
                    continue;
                }
                JsonObject obj = new JsonObject();
                obj.addProperty("section", section);
                obj.addProperty("exec_sql_text", text);
                StatementSerializer.addSpan(obj, execSql.getCtx());
                out.add(obj);
            } else if (entry instanceof DataDescriptionEntryGroup group) {
                collectExecSqlEntries(group.getDataDescriptionEntries(), section, out);
            } else {
                // Rename/Condition entries cannot themselves carry a nested
                // EXEC SQL entry, but logging here (rather than silently
                // matching nothing) means a future ProLeap entry kind that
                // COULD nest one does not repeat forge-qhi's silent-drop trap.
                LOG.fine("collectExecSqlEntries: not recursing into "
                        + entry.getClass().getName());
            }
        }
    }

    /**
     * Serializes a single DataDescriptionEntryGroup to a CobolField JSON object.
     */
    private JsonObject serializeGroup(DataDescriptionEntryGroup group, int offset) {
        JsonObject obj = new JsonObject();
        String fieldName = disambiguateFiller(group.getName());
        obj.addProperty("name", fieldName);
        if (isFiller(group.getName())) {
            obj.addProperty("filler", true);
        }
        obj.addProperty("level", group.getLevelNumber());
        obj.addProperty("pic", extractPic(group));
        obj.addProperty("usage", extractUsage(group));
        obj.addProperty("offset", offset);
        StatementSerializer.addSpan(obj, group.getCtx());

        String value = extractFirstValue(group);
        if (!value.isEmpty()) {
            obj.addProperty("value", value);
        }
        // Distinguish a figurative VALUE (SPACES, ZEROS, ...) — which fills the
        // whole field with its fill character — from a quoted literal that merely
        // looks like one (VALUE 'SPACE'). The figurative keyword is never quoted
        // in source (red-dragon-zuhj).
        if (isFigurativeValue(group)) {
            obj.addProperty("value_is_figurative", true);
        }
        if (isAllValue(group)) {
            obj.addProperty("value_is_all", true);
        }
        if (isNumericValue(group)) {
            obj.addProperty("value_is_numeric", true);
        }

        JsonArray valuesArray = extractAllValues(group);
        if (valuesArray.size() > 0) {
            obj.add("values", valuesArray);
        }

        String redefines = extractRedefines(group);
        if (!redefines.isEmpty()) {
            obj.addProperty("redefines", redefines);
        }

        int occursCount = extractOccurs(group);
        if (occursCount > 0) {
            obj.addProperty("occurs", occursCount);
            int elementSize = computeElementSize(group);
            obj.addProperty("element_size", elementSize);
        }

        List<String> indexNames = extractIndexNames(group);
        if (!indexNames.isEmpty()) {
            JsonArray arr = new JsonArray();
            for (String n : indexNames) {
                arr.add(n);
            }
            obj.add("indexed_by", arr);
        }

        int occursMin = extractOccursMin(group);
        if (occursMin > 0) {
            obj.addProperty("occurs_min", occursMin);
        }

        JsonObject dependingOn = extractOccursDependingOn(group);
        if (dependingOn != null) {
            obj.add("occurs_depending_on", dependingOn);
        }

        JsonObject signObj = extractSign(group);
        if (signObj != null) {
            obj.add("sign", signObj);
        }

        if (extractJustified(group)) {
            obj.addProperty("justified_right", true);
        }

        if (extractSynchronized(group)) {
            obj.addProperty("synchronized", true);
        }

        if (extractBlankWhenZero(group)) {
            obj.addProperty("blank_when_zero", true);
        }

        List<DataDescriptionEntry> children = group.getDataDescriptionEntries();
        if (children != null && !children.isEmpty()) {
            JsonArray childArray = serializeChildren(children);
            if (childArray.size() > 0) {
                obj.add("children", childArray);
            }

            JsonArray conditionsArray = serializeConditions(children);
            if (conditionsArray.size() > 0) {
                obj.add("conditions", conditionsArray);
            }
        }

        LOG.fine("Serialized field: " + fieldName + " level=" + group.getLevelNumber()
                + " pic=" + extractPic(group) + " offset=" + offset);
        return obj;
    }

    /**
     * Serializes a level-66 RENAMES entry to a CobolField JSON object.
     * RENAMES does not allocate storage — offset is set to 0 (resolved in Python).
     * The renamed items are structured references, OF/IN qualifiers included.
     */
    private JsonObject serializeRename(DataDescriptionEntryRename rename) {
        JsonObject obj = new JsonObject();
        String fieldName = disambiguateFiller(rename.getName());
        obj.addProperty("name", fieldName);
        obj.addProperty("level", 66);
        obj.addProperty("pic", "");
        obj.addProperty("usage", "DISPLAY");
        obj.addProperty("offset", 0);
        StatementSerializer.addSpan(obj, rename.getCtx());

        if (rename.getRenamesClause() != null) {
            if (rename.getRenamesClause().getFrom() != null) {
                obj.add("renames_from",
                        StatementSerializer.serializeRef(rename.getRenamesClause().getFrom()));
            }
            if (rename.getRenamesClause().getTo() != null) {
                obj.add("renames_thru",
                        StatementSerializer.serializeRef(rename.getRenamesClause().getTo()));
            }
        }

        LOG.fine("Serialized RENAMES field: " + fieldName);
        return obj;
    }

    /**
     * Disambiguates FILLER field names by appending a sequential counter.
     * "FILLER" becomes "FILLER_1", "FILLER_2", etc.
     */
    private static boolean isFiller(String name) {
        return name == null || "FILLER".equalsIgnoreCase(name);
    }

    private String disambiguateFiller(String name) {
        if (isFiller(name)) {
            fillerCount++;
            return "FILLER_" + fillerCount;
        }
        return name;
    }

    /**
     * Serializes child entries with running offset computation within the group.
     */
    private JsonArray serializeChildren(List<DataDescriptionEntry> children) {
        JsonArray childArray = new JsonArray();
        int childOffset = 0;

        for (DataDescriptionEntry child : children) {
            if (child instanceof DataDescriptionEntryGroup childGroup) {
                // SYNCHRONIZED: align offset to natural boundary for COMP/BINARY fields
                if (extractSynchronized(childGroup)) {
                    int alignment = computeSyncAlignment(childGroup);
                    if (alignment > 1 && childOffset % alignment != 0) {
                        childOffset += alignment - (childOffset % alignment);
                    }
                }

                int effectiveOffset = childOffset;
                if (childGroup.getRedefinesClause() != null) {
                    effectiveOffset = findRedefinesOffset(children, childGroup);
                }

                JsonObject childObj = serializeGroup(childGroup, effectiveOffset);
                childArray.add(childObj);

                if (childGroup.getRedefinesClause() == null) {
                    childOffset += computeByteLength(childGroup);
                }
            } else if (child instanceof DataDescriptionEntryRename rename) {
                JsonObject renameObj = serializeRename(rename);
                childArray.add(renameObj);
                // RENAMES does not allocate storage
            }
        }
        return childArray;
    }

    /**
     * Computes the natural alignment boundary for a SYNCHRONIZED field.
     * Returns the alignment in bytes (2, 4, or 8 for COMP/BINARY; 1 for others).
     */
    private static int computeSyncAlignment(DataDescriptionEntryGroup group) {
        String usage = extractUsage(group);
        return switch (usage) {
            case "COMP", "COMP-4", "BINARY", "COMP-5" ->
                    computePicByteLength(extractPic(group), usage);
            default -> 1;
        };
    }

    /**
     * Serializes level-88 condition entries from a list of children.
     * Returns a JSON array of condition objects, each with "name" and "values".
     */
    private JsonArray serializeConditions(List<DataDescriptionEntry> children) {
        JsonArray conditionsArray = new JsonArray();

        for (DataDescriptionEntry child : children) {
            if (child instanceof DataDescriptionEntryCondition condition) {
                JsonObject condObj = new JsonObject();
                condObj.addProperty("name", condition.getName());

                JsonArray valuesArray = new JsonArray();
                try {
                    if (condition.getValueClause() != null
                            && condition.getValueClause().getValueIntervals() != null) {
                        for (ValueInterval interval : condition.getValueClause().getValueIntervals()) {
                            valuesArray.add(serializeValueInterval(interval));
                        }
                    }
                } catch (Exception e) {
                    LOG.fine("Could not extract values for condition " + condition.getName()
                            + ": " + e.getMessage());
                }

                condObj.add("values", valuesArray);
                conditionsArray.add(condObj);
                LOG.fine("Serialized level-88 condition: " + condition.getName()
                        + " with " + valuesArray.size() + " value intervals");
            }
        }
        return conditionsArray;
    }

    /**
     * Serializes a single ValueInterval to a JSON object with "from" and "to" keys.
     */
    private static JsonObject serializeValueInterval(ValueInterval interval) {
        JsonObject intervalObj = new JsonObject();

        intervalObj.addProperty("from",
                stripQuotes(rawBoundText(fromLiteral(interval), interval.getFromValueStmt())));
        intervalObj.addProperty("to",
                stripQuotes(rawBoundText(toLiteral(interval), interval.getToValueStmt())));
        if (isAllLiteral(fromLiteral(interval))) {
            intervalObj.addProperty("all", true);
        }
        if (isNumericLiteral(fromLiteral(interval))) {
            intervalObj.addProperty("numeric", true);
        }
        return intervalObj;
    }

    private static boolean isNumericLiteral(CobolParser.LiteralContext lit) {
        return lit != null && unwrapAll(lit).numericLiteral() != null;
    }

    private static CobolParser.LiteralContext fromLiteral(ValueInterval interval) {
        return interval.getCtx() instanceof CobolParser.DataValueIntervalContext ctx
                ? ctx.dataValueIntervalFrom().literal() : null;
    }

    private static CobolParser.LiteralContext toLiteral(ValueInterval interval) {
        return interval.getCtx() instanceof CobolParser.DataValueIntervalContext ctx
                && ctx.dataValueIntervalTo() != null
                ? ctx.dataValueIntervalTo().literal() : null;
    }

    private static CobolParser.LiteralContext unwrapAll(CobolParser.LiteralContext lit) {
        CobolParser.LiteralContext repeated = StatementSerializer.allRepeatedLiteral(lit);
        return repeated != null ? unwrapAll(repeated) : lit;
    }

    private static String rawBoundText(CobolParser.LiteralContext lit, ValueStmt vs) {
        if (lit != null) {
            return unwrapAll(lit).getText();
        }
        return vs != null && vs.getCtx() != null ? vs.getCtx().getText() : "";
    }

    private static boolean isAllLiteral(CobolParser.LiteralContext lit) {
        return StatementSerializer.allRepeatedLiteral(lit) != null
                && unwrapAll(lit).figurativeConstant() == null;
    }

    private static boolean isAllValue(DataDescriptionEntryGroup group) {
        return group.getValueClause() != null
                && !group.getValueClause().getValueIntervals().isEmpty()
                && isAllLiteral(fromLiteral(group.getValueClause().getValueIntervals().get(0)));
    }

    /**
     * True when the item's VALUE is a numeric literal: an edited item edits a
     * numeric VALUE as a MOVE would, but stores a nonnumeric one verbatim.
     * The figurative ZERO is not a numeric literal.
     */
    private static boolean isNumericValue(DataDescriptionEntryGroup group) {
        if (group.getValueClause() == null
                || group.getValueClause().getValueIntervals().isEmpty()) {
            return false;
        }
        CobolParser.LiteralContext lit =
                fromLiteral(group.getValueClause().getValueIntervals().get(0));
        CobolParser.NumericLiteralContext numeric =
                lit == null ? null : unwrapAll(lit).numericLiteral();
        return numeric != null && numeric.ZERO() == null;
    }

    /**
     * A VALUE literal's characters: a nonnumeric literal loses its delimiters and
     * each doubled delimiter inside it stands for one; a numeric literal is
     * emitted as written.
     */
    private static String stripQuotes(String raw) {
        if (raw.length() >= 2
                && ((raw.startsWith("'") && raw.endsWith("'"))
                || (raw.startsWith("\"") && raw.endsWith("\"")))) {
            String delimiter = raw.substring(0, 1);
            return raw.substring(1, raw.length() - 1).replace(delimiter + delimiter, delimiter);
        }
        return raw;
    }

    /**
     * Finds the offset of the field being redefined.
     */
    private static int findRedefinesOffset(
            List<DataDescriptionEntry> siblings,
            DataDescriptionEntryGroup redefiningEntry) {
        String targetName = extractRedefines(redefiningEntry);
        int offset = 0;
        for (DataDescriptionEntry sibling : siblings) {
            if (sibling instanceof DataDescriptionEntryGroup siblingGroup) {
                // An anonymous FILLER sibling has a null name; it can never be
                // the redefines target, so skip the comparison (mirrors the
                // null-safe FILLER handling in disambiguateFiller).
                if (siblingGroup.getName() != null
                        && siblingGroup.getName().equalsIgnoreCase(targetName)) {
                    return offset;
                }
                if (siblingGroup.getRedefinesClause() == null) {
                    offset += computeByteLength(siblingGroup);
                }
            }
        }
        return 0;
    }

    /**
     * Computes byte length for a data entry.
     * Elementary items: derived from PIC string.
     * Group items: sum of non-REDEFINES children.
     */
    public static int computeByteLength(DataDescriptionEntryGroup group) {
        int baseLength = computeElementSize(group);
        int occursCount = extractOccurs(group);
        return (occursCount > 0) ? baseLength * occursCount : baseLength;
    }

    /**
     * Computes the byte length of a single element (without OCCURS multiplier).
     * For group items: sum of non-REDEFINES children.
     * For elementary items: derived from PIC string.
     */
    public static int computeElementSize(DataDescriptionEntryGroup group) {
        List<DataDescriptionEntry> children = group.getDataDescriptionEntries();
        if (children != null && !children.isEmpty()) {
            // Only treat as group item if there are actual DataDescriptionEntryGroup children.
            // Level-88 condition entries (DataDescriptionEntryCondition) are not real children
            // for size purposes — they don't occupy storage.
            List<DataDescriptionEntryGroup> groupChildren = children.stream()
                    .filter(c -> c instanceof DataDescriptionEntryGroup)
                    .map(c -> (DataDescriptionEntryGroup) c)
                    .filter(c -> c.getRedefinesClause() == null)
                    .collect(java.util.stream.Collectors.toList());
            if (!groupChildren.isEmpty()) {
                return groupChildren.stream()
                        .mapToInt(DataFieldSerializer::computeByteLength)
                        .sum();
            }
        }
        int baseLength = computePicByteLength(extractPic(group), extractUsage(group));
        JsonObject signObj = extractSign(group);
        if (signObj != null && signObj.get("separate").getAsBoolean()) {
            baseLength += 1;
        }
        return baseLength;
    }

    /**
     * Computes byte length from a PIC string and usage.
     *
     * <p>For DISPLAY usage: count of storage characters (9, X, A) with repetition.
     * For COMP-3: ceil((digits + 1) / 2).
     * For COMP/BINARY/COMP-5: 2 for ≤4 digits, 4 for ≤9, 8 for ≤18.
     */
    public static int computePicByteLength(String pic, String usage) {
        if ("POINTER".equals(usage)) {
            return pointerSize;
        }
        if ("INDEX".equals(usage)) {
            return INDEX_ITEM_SIZE;
        }
        if ("COMP-1".equals(usage)) {
            return COMP_1_SIZE;
        }
        if ("COMP-2".equals(usage)) {
            return COMP_2_SIZE;
        }
        if (pic.isEmpty()) {
            return 0;
        }

        int digitCount = countStoragePositions(pic);

        return switch (usage) {
            case "COMP-3", "PACKED-DECIMAL" -> (digitCount / 2) + 1;
            case "COMP", "COMP-4", "BINARY", "COMP-5" -> {
                if (digitCount <= 4) yield 2;
                else if (digitCount <= 9) yield 4;
                else yield 8;
            }
            default -> digitCount;
        };
    }

    /**
     * Counts storage positions (digits/chars) from a PIC string.
     * Handles: 9(5) → 5, X(3) → 3, S9(5)V99 → 7, etc.
     *
     * <p>Numeric-edited pictures (sign, Z suppression, comma/decimal insertion)
     * store the formatted character string, so every position — including the
     * sign, '.', and ',' — occupies a byte. These are sized by their full
     * character width (mirroring Python edit_picture.parse_edit_picture().width).
     */
    public static int countStoragePositions(String pic) {
        String upper = pic.toUpperCase();
        int count = 0;
        int i = 0;
        char previous = 0;
        while (i < upper.length()) {
            char c = upper.charAt(i);
            if (c == '(') {
                int close = upper.indexOf(')', i);
                int repeat = Integer.parseInt(upper.substring(i + 1, close));
                // The preceding symbol already contributed 1 — add the remainder,
                // but only if that symbol occupies storage at all (P(3) is still 0).
                if (isStoredPosition(previous)) {
                    count += repeat - 1;
                }
                i = close + 1;
            } else {
                if (isStoredPosition(c)) {
                    count += 1;
                }
                previous = c;
                i++;
            }
        }
        return count;
    }

    /**
     * True if a PIC symbol occupies a storage position.
     *
     * <p>S (operational sign), V (implied decimal point) and P (decimal scaling)
     * are the only PIC symbols that occupy none. Everything else — digits, Z,
     * currency, check protection, and every insertion character — is one byte.
     */
    private static boolean isStoredPosition(char c) {
        return c != 'S' && c != 'V' && c != 'P';
    }

    private static String extractPic(DataDescriptionEntryGroup group) {
        try {
            if (group.getPictureClause() != null) {
                return group.getPictureClause().getPictureString();
            }
        } catch (Exception e) {
            LOG.fine("No PIC clause for " + group.getName());
        }
        return "";
    }

    /**
     * The item's USAGE: its own clause, else the nearest enclosing group's, else
     * DISPLAY. "The USAGE clause written at the group level applies to each
     * elementary item in the group" (ANSI X3.23-1985 / ISO 1989 USAGE clause).
     */
    private static String extractUsage(DataDescriptionEntryGroup group) {
        if (group.getUsageClause() != null && group.getUsageClause().getUsageClauseType() != null) {
            return mapUsageType(group.getUsageClause().getUsageClauseType().name());
        }
        DataDescriptionEntryGroup parent = group.getParentDataDescriptionEntryGroup();
        return parent != null ? extractUsage(parent) : "DISPLAY";
    }

    /**
     * Maps ProLeap usage clause type names to standard COBOL usage strings.
     */
    private static String mapUsageType(String proleapType) {
        return switch (proleapType) {
            case "COMP_3", "PACKED_DECIMAL" -> "COMP-3";
            case "COMP", "COMP_4", "BINARY" -> "COMP";
            case "COMP_1" -> "COMP-1";
            case "COMP_2" -> "COMP-2";
            case "COMP_5" -> "COMP-5";
            case "DISPLAY_1" -> "DISPLAY-1";
            case "INDEX" -> "INDEX";
            case "NATIONAL" -> "NATIONAL";
            case "POINTER" -> "POINTER";
            default -> "DISPLAY";
        };
    }

    /**
     * Extracts the first value from a VALUE clause (backward compatibility).
     */
    private static String extractFirstValue(DataDescriptionEntryGroup group) {
        try {
            if (group.getValueClause() != null && !group.getValueClause().getValueIntervals().isEmpty()) {
                ValueInterval interval = group.getValueClause().getValueIntervals().get(0);
                return stripQuotes(rawBoundText(fromLiteral(interval), interval.getFromValueStmt()));
            }
        } catch (Exception e) {
            LOG.fine("No VALUE clause for " + group.getName());
        }
        return "";
    }

    private static final java.util.Set<String> FIGURATIVE_KEYWORDS = java.util.Set.of(
            "SPACE", "SPACES", "ZERO", "ZEROS", "ZEROES", "QUOTE", "QUOTES",
            "LOW-VALUE", "LOW-VALUES", "HIGH-VALUE", "HIGH-VALUES");

    /**
     * True when the group's VALUE clause is an (unquoted) figurative constant,
     * as opposed to a quoted literal. The raw source text is inspected before
     * quote stripping so VALUE 'SPACE' is NOT treated as figurative.
     */
    private static boolean isFigurativeValue(DataDescriptionEntryGroup group) {
        try {
            if (group.getValueClause() != null
                    && !group.getValueClause().getValueIntervals().isEmpty()) {
                ValueInterval interval = group.getValueClause().getValueIntervals().get(0);
                String raw = rawBoundText(fromLiteral(interval), interval.getFromValueStmt());
                boolean quoted = raw.length() >= 2
                        && ((raw.startsWith("'") && raw.endsWith("'"))
                        || (raw.startsWith("\"") && raw.endsWith("\"")));
                return !quoted && FIGURATIVE_KEYWORDS.contains(raw.toUpperCase());
            }
        } catch (Exception e) {
            LOG.fine("Could not determine figurative VALUE for " + group.getName());
        }
        return false;
    }

    /**
     * Extracts all value intervals from a VALUE clause as a JSON array
     * of {"from": ..., "to": ...} objects.
     */
    private static JsonArray extractAllValues(DataDescriptionEntryGroup group) {
        JsonArray valuesArray = new JsonArray();
        try {
            if (group.getValueClause() != null
                    && group.getValueClause().getValueIntervals() != null
                    && !group.getValueClause().getValueIntervals().isEmpty()) {
                for (ValueInterval interval : group.getValueClause().getValueIntervals()) {
                    valuesArray.add(serializeValueInterval(interval));
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract all values for " + group.getName());
        }
        return valuesArray;
    }

    private static String extractRedefines(DataDescriptionEntryGroup group) {
        try {
            if (group.getRedefinesClause() != null) {
                return group.getRedefinesClause().getRedefinesCall().getName();
            }
        } catch (Exception e) {
            LOG.fine("No REDEFINES clause for " + group.getName());
        }
        return "";
    }

    /**
     * Extracts the SYNCHRONIZED clause from a data description entry.
     * Returns true if SYNCHRONIZED is present.
     */
    private static boolean extractSynchronized(DataDescriptionEntryGroup group) {
        try {
            SynchronizedClause syncClause = group.getSynchronizedClause();
            return syncClause != null;
        } catch (Exception e) {
            LOG.fine("No SYNCHRONIZED clause for " + group.getName());
        }
        return false;
    }

    /**
     * Extracts the JUSTIFIED clause from a data description entry.
     * Returns true if JUSTIFIED RIGHT is present.
     */
    private static boolean extractJustified(DataDescriptionEntryGroup group) {
        try {
            JustifiedClause justifiedClause = group.getJustifiedClause();
            return justifiedClause != null;
        } catch (Exception e) {
            LOG.fine("No JUSTIFIED clause for " + group.getName());
        }
        return false;
    }

    /**
     * Extracts the BLANK WHEN ZERO clause from a data description entry.
     * Returns true if BLANK WHEN ZERO is present.
     */
    private static boolean extractBlankWhenZero(DataDescriptionEntryGroup group) {
        try {
            BlankWhenZeroClause blankClause = group.getBlankWhenZeroClause();
            return blankClause != null;
        } catch (Exception e) {
            LOG.fine("No BLANK WHEN ZERO clause for " + group.getName());
        }
        return false;
    }

    /**
     * The item's SIGN clause as a JSON object with "position" ("LEADING"/"TRAILING")
     * and "separate" (boolean): its own clause, else, for a signed numeric DISPLAY
     * item, the nearest enclosing group's; null if neither applies. "The SIGN clause
     * specified at group level applies to each signed numeric data description entry
     * subordinate to that group; one specified at a subordinate level takes
     * precedence" (ANSI X3.23-1985 / ISO 1989 SIGN clause, VI-42 5.12.4).
     */
    private static JsonObject extractSign(DataDescriptionEntryGroup group) {
        SignClause own = group.getSignClause();
        if (own != null && own.getSignClauseType() != null) {
            return signJson(own);
        }
        if (!isSignedDisplayNumeric(group)) {
            return null;
        }
        SignClause inherited = nearestGroupSign(group.getParentDataDescriptionEntryGroup());
        return inherited != null ? signJson(inherited) : null;
    }

    private static SignClause nearestGroupSign(DataDescriptionEntryGroup group) {
        if (group == null) {
            return null;
        }
        SignClause sign = group.getSignClause();
        if (sign != null && sign.getSignClauseType() != null) {
            return sign;
        }
        return nearestGroupSign(group.getParentDataDescriptionEntryGroup());
    }

    private static boolean isSignedDisplayNumeric(DataDescriptionEntryGroup group) {
        return extractPic(group).toUpperCase().startsWith("S")
                && "DISPLAY".equals(extractUsage(group));
    }

    private static JsonObject signJson(SignClause signClause) {
        JsonObject signObj = new JsonObject();
        String position = signClause.getSignClauseType() == SignClause.SignClauseType.LEADING
                ? "LEADING" : "TRAILING";
        signObj.addProperty("position", position);
        signObj.addProperty("separate", signClause.isSeparate());
        return signObj;
    }

    /**
     * Extracts the OCCURS count from a data description entry.
     * For OCCURS DEPENDING ON, returns the max count (from getTo()).
     * For fixed OCCURS, returns getFrom() (the only count).
     * Returns 0 if no OCCURS clause is present.
     */
    private static int extractOccurs(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                // If DEPENDING ON is present, getTo() is the max count
                if (clause.getOccursDepending() != null && clause.getTo() != null) {
                    return Integer.parseInt(clause.getTo().getCtx().getText());
                }
                // Fixed OCCURS: the count is in getFrom()
                if (clause.getFrom() != null && clause.getFrom().getCtx() != null) {
                    return Integer.parseInt(clause.getFrom().getCtx().getText());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract OCCURS for " + group.getName() + ": " + e.getMessage());
        }
        return 0;
    }

    /**
     * The INDEXED BY names on a group's OccursClause, in declaration order.
     *
     * <p>An index declared this way is compiler-allocated: there is deliberately no
     * `01 IX PIC ...` anywhere, so this clause is the item's only declaration. Order
     * matters — a Format 1 SEARCH with no VARYING advances the FIRST index. Names are
     * preserved verbatim as declared, matching every other identifier extractor in
     * this class (e.g. {@code extractRedefines}, {@code extractOccursDependingOn}) —
     * case-insensitive matching is done by callers, not by upper-casing here.
     */
    private static List<String> extractIndexNames(DataDescriptionEntryGroup group) {
        List<String> names = new ArrayList<>();
        try {
            List<OccursClause> clauses = group.getOccursClauses();
            if (clauses == null || clauses.isEmpty()) {
                return names;
            }
            OccursIndexed indexed = clauses.get(0).getOccursIndexed();
            if (indexed == null || indexed.getIndices() == null) {
                return names;
            }
            for (Index ix : indexed.getIndices()) {
                if (ix.getName() != null) {
                    names.add(ix.getName());
                }
            }
        } catch (Exception e) {
            LOG.fine("No INDEXED BY names: " + e.getMessage());
        }
        return names;
    }

    /**
     * Extracts the minimum OCCURS count for OCCURS DEPENDING ON.
     * Returns 0 if no DEPENDING ON clause or no minimum specified.
     */
    private static int extractOccursMin(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                if (clause.getOccursDepending() != null
                        && clause.getFrom() != null
                        && clause.getFrom().getCtx() != null) {
                    return Integer.parseInt(clause.getFrom().getCtx().getText());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract OCCURS min for " + group.getName() + ": " + e.getMessage());
        }
        return 0;
    }

    /**
     * Extracts the DEPENDING ON object of an OCCURS clause as a structured
     * reference, OF/IN qualifiers included. Returns null if no DEPENDING ON
     * clause is present.
     */
    private static JsonObject extractOccursDependingOn(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                if (clause.getOccursDepending() != null
                        && clause.getOccursDepending().getDependingOnCall() != null) {
                    return StatementSerializer.serializeRef(
                            clause.getOccursDepending().getDependingOnCall());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DEPENDING ON for " + group.getName() + ": " + e.getMessage());
        }
        return null;
    }
}
