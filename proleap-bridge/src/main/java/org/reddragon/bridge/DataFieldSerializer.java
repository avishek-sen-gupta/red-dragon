package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntry;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryCondition;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryGroup;
import io.proleap.cobol.asg.metamodel.data.datadescription.OccursClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.SignClause;
import io.proleap.cobol.asg.metamodel.data.datadescription.ValueInterval;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;

import java.util.List;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Serializes DATA DIVISION entries to JSON matching the CobolField contract.
 *
 * <p>Computes byte offsets using a running accumulator, mirroring the Python
 * {@code data_layout.py} offset logic. ProLeap does not compute offsets natively.
 */
public final class DataFieldSerializer {

    private static final Logger LOG = Logger.getLogger(DataFieldSerializer.class.getName());

    /**
     * Pattern for PIC repetition notation: X(5), 9(3), S9(5)V99, etc.
     * Matches individual PIC characters optionally followed by (count).
     */
    private static final Pattern PIC_TOKEN_PATTERN =
            Pattern.compile("([SsVv])|([9AaXx])(?:\\((\\d+)\\))?");

    /** Running counter for disambiguating FILLER fields within a serialization session. */
    private int fillerCount = 0;

    private DataFieldSerializer() {
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

        for (DataDescriptionEntry entry : entries) {
            if (entry instanceof DataDescriptionEntryGroup group) {
                JsonObject field = instance.serializeGroup(group, runningOffset);
                fields.add(field);

                boolean isRedefines = group.getRedefinesClause() != null;
                if (!isRedefines) {
                    runningOffset += computeByteLength(group);
                }
            }
        }
        return fields;
    }

    /**
     * Serializes a single DataDescriptionEntryGroup to a CobolField JSON object.
     */
    private JsonObject serializeGroup(DataDescriptionEntryGroup group, int offset) {
        JsonObject obj = new JsonObject();
        String fieldName = disambiguateFiller(group.getName());
        obj.addProperty("name", fieldName);
        obj.addProperty("level", group.getLevelNumber());
        obj.addProperty("pic", extractPic(group));
        obj.addProperty("usage", extractUsage(group));
        obj.addProperty("offset", offset);

        String value = extractFirstValue(group);
        if (!value.isEmpty()) {
            obj.addProperty("value", value);
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

        JsonObject signObj = extractSign(group);
        if (signObj != null) {
            obj.add("sign", signObj);
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
     * Disambiguates FILLER field names by appending a sequential counter.
     * "FILLER" becomes "FILLER_1", "FILLER_2", etc.
     */
    private String disambiguateFiller(String name) {
        if (name == null || "FILLER".equalsIgnoreCase(name)) {
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
                int effectiveOffset = childOffset;
                if (childGroup.getRedefinesClause() != null) {
                    effectiveOffset = findRedefinesOffset(children, childGroup);
                }

                JsonObject childObj = serializeGroup(childGroup, effectiveOffset);
                childArray.add(childObj);

                if (childGroup.getRedefinesClause() == null) {
                    childOffset += computeByteLength(childGroup);
                }
            }
        }
        return childArray;
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

        ValueStmt fromVs = interval.getFromValueStmt();
        if (fromVs != null && fromVs.getCtx() != null) {
            intervalObj.addProperty("from", stripQuotes(fromVs.getCtx().getText()));
        } else {
            intervalObj.addProperty("from", "");
        }

        ValueStmt toVs = interval.getToValueStmt();
        if (toVs != null && toVs.getCtx() != null) {
            intervalObj.addProperty("to", stripQuotes(toVs.getCtx().getText()));
        } else {
            intervalObj.addProperty("to", "");
        }

        return intervalObj;
    }

    /**
     * Strips surrounding quotes from a string literal.
     */
    private static String stripQuotes(String raw) {
        if (raw.length() >= 2
                && ((raw.startsWith("'") && raw.endsWith("'"))
                || (raw.startsWith("\"") && raw.endsWith("\"")))) {
            return raw.substring(1, raw.length() - 1);
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
                if (siblingGroup.getName().equalsIgnoreCase(targetName)) {
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
     * For COMP/BINARY: 2 for ≤4 digits, 4 for ≤9, 8 for ≤18.
     */
    public static int computePicByteLength(String pic, String usage) {
        if (pic.isEmpty()) {
            return 0;
        }

        int digitCount = countStoragePositions(pic);

        return switch (usage) {
            case "COMP-3", "PACKED-DECIMAL" -> (digitCount / 2) + 1;
            case "COMP", "COMP-4", "BINARY" -> {
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
     */
    public static int countStoragePositions(String pic) {
        int count = 0;
        Matcher matcher = PIC_TOKEN_PATTERN.matcher(pic.toUpperCase());

        while (matcher.find()) {
            if (matcher.group(1) != null) {
                // S or V — no storage position
                continue;
            }
            String countStr = matcher.group(3);
            count += (countStr != null) ? Integer.parseInt(countStr) : 1;
        }
        return count;
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

    private static String extractUsage(DataDescriptionEntryGroup group) {
        try {
            if (group.getUsageClause() != null && group.getUsageClause().getUsageClauseType() != null) {
                return mapUsageType(group.getUsageClause().getUsageClauseType().name());
            }
        } catch (Exception e) {
            LOG.fine("No USAGE clause for " + group.getName());
        }
        return "DISPLAY";
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
                ValueStmt fromVs = interval.getFromValueStmt();
                if (fromVs != null && fromVs.getCtx() != null) {
                    return stripQuotes(fromVs.getCtx().getText());
                }
            }
        } catch (Exception e) {
            LOG.fine("No VALUE clause for " + group.getName());
        }
        return "";
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
     * Extracts the SIGN clause from a data description entry.
     * Returns a JSON object with "position" ("LEADING"/"TRAILING") and "separate" (boolean),
     * or null if no SIGN clause is present.
     */
    private static JsonObject extractSign(DataDescriptionEntryGroup group) {
        try {
            SignClause signClause = group.getSignClause();
            if (signClause != null && signClause.getSignClauseType() != null) {
                JsonObject signObj = new JsonObject();
                String position = signClause.getSignClauseType() == SignClause.SignClauseType.LEADING
                        ? "LEADING" : "TRAILING";
                signObj.addProperty("position", position);
                signObj.addProperty("separate", signClause.isSeparate());
                return signObj;
            }
        } catch (Exception e) {
            LOG.fine("No SIGN clause for " + group.getName());
        }
        return null;
    }

    /**
     * Extracts the OCCURS count from a data description entry.
     * Returns 0 if no OCCURS clause is present.
     */
    private static int extractOccurs(DataDescriptionEntryGroup group) {
        try {
            List<OccursClause> occursClauses = group.getOccursClauses();
            if (occursClauses != null && !occursClauses.isEmpty()) {
                OccursClause clause = occursClauses.get(0);
                if (clause.getFrom() != null && clause.getFrom().getCtx() != null) {
                    return Integer.parseInt(clause.getFrom().getCtx().getText());
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract OCCURS for " + group.getName() + ": " + e.getMessage());
        }
        return 0;
    }
}
