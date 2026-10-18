package org.reddragon.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;
import io.proleap.cobol.asg.metamodel.Scope;
import io.proleap.cobol.asg.metamodel.procedure.NotOnSizeErrorPhrase;
import io.proleap.cobol.asg.metamodel.procedure.OnSizeErrorPhrase;
import io.proleap.cobol.asg.metamodel.procedure.Statement;
import io.proleap.cobol.asg.metamodel.procedure.StatementType;
import io.proleap.cobol.asg.metamodel.procedure.StatementTypeEnum;
import io.proleap.cobol.asg.metamodel.procedure.add.AddStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.AddToGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.AddToStatement;
import io.proleap.cobol.asg.metamodel.procedure.add.From;
import io.proleap.cobol.asg.metamodel.procedure.add.To;
import io.proleap.cobol.asg.metamodel.procedure.add.ToGiving;
import io.proleap.cobol.asg.metamodel.procedure.compute.ComputeStatement;
import io.proleap.cobol.asg.metamodel.procedure.compute.Store;
import io.proleap.cobol.asg.metamodel.procedure.continuestmt.ContinueStatement;
import io.proleap.cobol.asg.metamodel.procedure.display.DisplayStatement;
import io.proleap.cobol.asg.metamodel.procedure.display.Operand;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideByGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideIntoGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideIntoStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.DivideStatement;
import io.proleap.cobol.asg.metamodel.procedure.divide.Giving;
import io.proleap.cobol.asg.metamodel.procedure.divide.GivingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.divide.Into;
import io.proleap.cobol.asg.metamodel.procedure.divide.Remainder;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.AlsoCondition;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.AlsoSelect;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.EvaluateStatement;
import io.proleap.cobol.asg.metamodel.procedure.evaluate.WhenPhrase;
import io.proleap.cobol.asg.metamodel.procedure.exit.ExitStatement;
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.GoToStatement;
import io.proleap.cobol.asg.metamodel.procedure.gotostmt.DependingOnPhrase;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.IfStatement;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.Then;
import io.proleap.cobol.asg.metamodel.procedure.ifstmt.Else;
import io.proleap.cobol.asg.metamodel.procedure.initialize.By;
import io.proleap.cobol.asg.metamodel.procedure.initialize.InitializeStatement;
import io.proleap.cobol.asg.metamodel.procedure.inspect.AllLeading;
import io.proleap.cobol.asg.metamodel.procedure.inspect.AllLeadingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.inspect.InspectStatement;
import io.proleap.cobol.asg.metamodel.procedure.inspect.ReplacingAllLeading;
import io.proleap.cobol.asg.metamodel.procedure.inspect.ReplacingAllLeadings;
import io.proleap.cobol.asg.metamodel.procedure.open.OpenStatement;
import io.proleap.cobol.asg.metamodel.procedure.read.ReadStatement;
import io.proleap.cobol.asg.metamodel.procedure.sort.SortStatement;
import io.proleap.cobol.asg.metamodel.procedure.merge.MergeStatement;
import io.proleap.cobol.asg.metamodel.procedure.release.ReleaseStatement;
import io.proleap.cobol.asg.metamodel.procedure.returnstmt.ReturnStatement;
import io.proleap.cobol.asg.metamodel.procedure.search.SearchStatement;
import io.proleap.cobol.asg.metamodel.procedure.alter.AlterStatement;
import io.proleap.cobol.asg.metamodel.procedure.alter.ProceedTo;
import io.proleap.cobol.asg.metamodel.procedure.goback.GobackStatement;
import io.proleap.cobol.asg.metamodel.procedure.call.ByContent;
import io.proleap.cobol.asg.metamodel.procedure.call.ByReference;
import io.proleap.cobol.asg.metamodel.procedure.call.ByValue;
import io.proleap.cobol.asg.metamodel.procedure.call.CallStatement;
import io.proleap.cobol.asg.metamodel.procedure.call.UsingParameter;
import io.proleap.cobol.asg.metamodel.procedure.accept.AcceptStatement;
import io.proleap.cobol.asg.metamodel.procedure.cancel.CancelStatement;
import io.proleap.cobol.asg.metamodel.procedure.close.CloseStatement;
import io.proleap.cobol.asg.metamodel.procedure.entry.EntryStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveStatement.MoveType;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToStatement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveToSendingArea;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveCorrespondingToStatetement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveCorrespondingToSendingArea;
import io.proleap.cobol.asg.metamodel.procedure.multiply.ByOperand;
import io.proleap.cobol.asg.metamodel.procedure.multiply.MultiplyStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformInlineStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformProcedureStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.ByPhrase;
import io.proleap.cobol.asg.metamodel.procedure.perform.FromPhrase;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformType;
import io.proleap.cobol.asg.metamodel.procedure.perform.TestClause;
import io.proleap.cobol.asg.metamodel.procedure.perform.Times;
import io.proleap.cobol.asg.metamodel.procedure.perform.Until;
import io.proleap.cobol.asg.metamodel.procedure.perform.Varying;
import io.proleap.cobol.asg.metamodel.procedure.perform.VaryingClause;
import io.proleap.cobol.asg.metamodel.procedure.perform.After;
import io.proleap.cobol.asg.metamodel.procedure.perform.VaryingPhrase;
import io.proleap.cobol.asg.metamodel.procedure.set.SetBy;
import io.proleap.cobol.asg.metamodel.procedure.set.SetStatement;
import io.proleap.cobol.asg.metamodel.procedure.set.SetTo;
import io.proleap.cobol.asg.metamodel.procedure.stop.StopStatement;
import io.proleap.cobol.asg.metamodel.procedure.string.DelimitedByPhrase;
import io.proleap.cobol.asg.metamodel.procedure.string.Sendings;
import io.proleap.cobol.asg.metamodel.procedure.string.StringStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.MinuendGiving;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractFromStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractFromGivingStatement;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Minuend;
import io.proleap.cobol.asg.metamodel.procedure.subtract.Subtrahend;
import io.proleap.cobol.asg.metamodel.procedure.unstring.UnstringStatement;
import io.proleap.cobol.asg.metamodel.procedure.write.WriteStatement;
import io.proleap.cobol.asg.metamodel.procedure.delete.DeleteStatement;
import io.proleap.cobol.asg.metamodel.procedure.rewrite.RewriteStatement;
import io.proleap.cobol.asg.metamodel.procedure.start.StartStatement;
import io.proleap.cobol.asg.metamodel.procedure.execcics.ExecCicsStatement;
import io.proleap.cobol.asg.metamodel.procedure.execsql.ExecSqlStatement;
import io.proleap.cobol.asg.metamodel.procedure.xml.XmlGenerateStatement;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.call.DataDescriptionEntryCall;
import io.proleap.cobol.asg.metamodel.data.datadescription.DataDescriptionEntryCondition;
import io.proleap.cobol.asg.metamodel.call.SpecialRegisterCall;
import io.proleap.cobol.asg.metamodel.call.TableCall;
import io.proleap.cobol.asg.metamodel.valuestmt.ArithmeticValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.CallValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.ConditionValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.RelationConditionValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.Subscript;
import io.proleap.cobol.asg.metamodel.valuestmt.ValueStmt;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.Basis;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.MultDiv;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.MultDivs;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.PlusMinus;
import io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.Powers;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.AndOrCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.CombinableCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.ClassCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.ConditionNameReference;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.ConditionNameSubscriptReference;
import io.proleap.cobol.asg.metamodel.valuestmt.condition.SimpleCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.LiteralValueStmt;
import io.proleap.cobol.asg.metamodel.Literal;
import io.proleap.cobol.asg.metamodel.FigurativeConstant;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.ArithmeticComparison;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.CombinedComparison;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.CombinedCondition;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.RelationalOperator;
import io.proleap.cobol.asg.metamodel.valuestmt.relation.SignCondition;

import io.proleap.cobol.asg.metamodel.impl.ASGElementImpl;
import io.proleap.cobol.CobolParser;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.tree.ParseTree;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Logger;

/**
 * Serializes PROCEDURE DIVISION statements to JSON matching the CobolStatement contract.
 *
 * <p>Dispatches on {@code StatementType} and extracts operands, conditions,
 * and nested children for each statement type.
 */
public final class StatementSerializer {

    private static final Logger LOG = Logger.getLogger(StatementSerializer.class.getName());

    private StatementSerializer() {
    }

    /**
     * Adds the four flat position keys for a parser context, or nothing when
     * the context is absent. Shared with DataFieldSerializer so every
     * positioned object in the ASG uses one spelling.
     */
    static void addSpan(JsonObject obj, org.antlr.v4.runtime.ParserRuleContext ctx) {
        if (ctx == null || ctx.getStart() == null || ctx.getStop() == null) {
            return;
        }
        obj.addProperty("line_start", ctx.getStart().getLine());
        obj.addProperty("col_start",  ctx.getStart().getCharPositionInLine());
        obj.addProperty("line_end",   ctx.getStop().getLine());
        obj.addProperty("col_end",    ctx.getStop().getCharPositionInLine());
    }

    private static void addPhrase(JsonObject obj, String field, Scope phrase) {
        if (phrase != null) {
            obj.add(field, serializeStatements(phrase.getStatements()));
        }
    }

    /**
     * Serializes a list of statements to a JSON array.
     */
    public static JsonArray serializeStatements(List<Statement> statements) {
        JsonArray arr = new JsonArray();
        for (Statement stmt : statements) {
            JsonObject obj = serializeStatement(stmt);
            if (obj != null) {
                addSpan(obj, stmt.getCtx());
                arr.add(obj);
            }
        }
        return arr;
    }

    /**
     * NEXT SENTENCE, which ProLeap keeps only as a flag on an IF arm or a SEARCH
     * WHEN; spanned by that arm, the nearest construct that has a context.
     */
    private static JsonObject nextSentence(ParserRuleContext ctx) {
        JsonObject obj = newStatement("NEXT_SENTENCE");
        addSpan(obj, ctx);
        return obj;
    }

    /**
     * A paragraph's statements, and the position in that list of each sentence's
     * last statement: where the period falls. Positions count serialised
     * statements, since serializeStatements drops any it cannot serialise.
     */
    public static void serializeSentences(List<Statement> statements, JsonObject into) {
        JsonArray stmts = new JsonArray();
        JsonArray ends = new JsonArray();
        ParserRuleContext current = null;
        for (Statement stmt : statements) {
            ParserRuleContext sentence = sentenceOf(stmt.getCtx());
            if (current != null && sentence != current) {
                endSentence(stmts, ends);
            }
            current = sentence;
            JsonObject obj = serializeStatement(stmt);
            if (obj != null) {
                addSpan(obj, stmt.getCtx());
                stmts.add(obj);
            }
        }
        endSentence(stmts, ends);
        if (stmts.size() > 0) {
            into.add("statements", stmts);
            into.add("sentence_ends", ends);
        }
    }

    private static void endSentence(JsonArray stmts, JsonArray ends) {
        int last = stmts.size() - 1;
        if (last < 0) {
            return;
        }
        if (ends.size() > 0 && ends.get(ends.size() - 1).getAsInt() == last) {
            return;
        }
        ends.add(last);
    }

    private static ParserRuleContext sentenceOf(ParserRuleContext ctx) {
        ParserRuleContext at = ctx;
        while (at != null && !(at instanceof CobolParser.SentenceContext)) {
            at = at.getParent();
        }
        return at;
    }

    /**
     * Serializes a single Statement to a CobolStatement JSON object.
     */
    public static JsonObject serializeStatement(Statement stmt) {
        StatementType stmtType = stmt.getStatementType();
        LOG.fine("Serializing statement: " + stmtType);

        if (stmtType == StatementTypeEnum.MOVE) return serializeMove((MoveStatement) stmt);
        if (stmtType == StatementTypeEnum.ADD) return serializeAdd((AddStatement) stmt);
        if (stmtType == StatementTypeEnum.SUBTRACT) return serializeSubtract((SubtractStatement) stmt);
        if (stmtType == StatementTypeEnum.MULTIPLY) return serializeMultiply((MultiplyStatement) stmt);
        if (stmtType == StatementTypeEnum.DIVIDE) return serializeDivide((DivideStatement) stmt);
        if (stmtType == StatementTypeEnum.COMPUTE) return serializeCompute((ComputeStatement) stmt);
        if (stmtType == StatementTypeEnum.IF) return serializeIf((IfStatement) stmt);
        if (stmtType == StatementTypeEnum.PERFORM) return serializePerform((PerformStatement) stmt);
        if (stmtType == StatementTypeEnum.DISPLAY) return serializeDisplay((DisplayStatement) stmt);
        if (stmtType == StatementTypeEnum.STOP) return serializeStop((StopStatement) stmt);
        if (stmtType == StatementTypeEnum.GO_TO) return serializeGoTo((GoToStatement) stmt);
        if (stmtType == StatementTypeEnum.EVALUATE) return serializeEvaluate((EvaluateStatement) stmt);
        if (stmtType == StatementTypeEnum.CONTINUE) return serializeContinue((ContinueStatement) stmt);
        if (stmtType == StatementTypeEnum.EXIT) return serializeExit((ExitStatement) stmt);
        if (stmtType == StatementTypeEnum.GO_BACK) return serializeGoback((GobackStatement) stmt);
        if (stmtType == StatementTypeEnum.INITIALIZE) return serializeInitialize((InitializeStatement) stmt);
        if (stmtType == StatementTypeEnum.SET) return serializeSet((SetStatement) stmt);
        if (stmtType == StatementTypeEnum.STRING) return serializeString((StringStatement) stmt);
        if (stmtType == StatementTypeEnum.UNSTRING) return serializeUnstring((UnstringStatement) stmt);
        if (stmtType == StatementTypeEnum.INSPECT) return serializeInspect((InspectStatement) stmt);
        if (stmtType == StatementTypeEnum.SEARCH) return serializeSearch((SearchStatement) stmt);
        if (stmtType == StatementTypeEnum.CALL) return serializeCall((CallStatement) stmt);
        if (stmtType == StatementTypeEnum.ALTER) return serializeAlter((AlterStatement) stmt);
        if (stmtType == StatementTypeEnum.ENTRY) return serializeEntry((EntryStatement) stmt);
        if (stmtType == StatementTypeEnum.CANCEL) return serializeCancel((CancelStatement) stmt);
        if (stmtType == StatementTypeEnum.ACCEPT) return serializeAccept((AcceptStatement) stmt);
        if (stmtType == StatementTypeEnum.OPEN) return serializeOpen((OpenStatement) stmt);
        if (stmtType == StatementTypeEnum.CLOSE) return serializeClose((CloseStatement) stmt);
        if (stmtType == StatementTypeEnum.READ) return serializeRead((ReadStatement) stmt);
        if (stmtType == StatementTypeEnum.WRITE) return serializeWrite((WriteStatement) stmt);
        if (stmtType == StatementTypeEnum.REWRITE) return serializeRewrite((RewriteStatement) stmt);
        if (stmtType == StatementTypeEnum.START) return serializeStart((StartStatement) stmt);
        if (stmtType == StatementTypeEnum.DELETE) return serializeDelete((DeleteStatement) stmt);
        if (stmtType == StatementTypeEnum.EXEC_CICS) return serializeExecCics((ExecCicsStatement) stmt);
        if (stmtType == StatementTypeEnum.EXEC_SQL) return serializeExecSql((ExecSqlStatement) stmt);
        if (stmtType == StatementTypeEnum.XML_GENERATE) return serializeXmlGenerate((XmlGenerateStatement) stmt);
        if (stmtType == StatementTypeEnum.SORT) return SortSerializer.serializeSort((SortStatement) stmt);
        if (stmtType == StatementTypeEnum.MERGE) return SortSerializer.serializeMerge((MergeStatement) stmt);
        if (stmtType == StatementTypeEnum.RELEASE) return SortSerializer.serializeRelease((ReleaseStatement) stmt);
        if (stmtType == StatementTypeEnum.RETURN) return SortSerializer.serializeReturn((ReturnStatement) stmt);

        return serializeUnknown(stmtType);
    }

    private static JsonObject serializeMove(MoveStatement stmt) {
        // Handle MOVE CORRESPONDING separately
        if (stmt.getMoveType() == MoveType.MOVE_CORRESPONDING) {
            JsonObject obj = newStatement("MOVE_CORRESPONDING");
            MoveCorrespondingToStatetement corr = stmt.getMoveCorrespondingToStatement();
            if (corr != null) {
                MoveCorrespondingToSendingArea sendingArea = corr.getMoveToCorrespondingSendingArea();
                if (sendingArea != null) {
                    Call sourceCall = sendingArea.getSendingAreaCall();
                    if (sourceCall != null) {
                        obj.add("source", serializeRef(sourceCall));
                    }
                }
                JsonArray targets = new JsonArray();
                for (Call receivingCall : corr.getReceivingAreaCalls()) {
                    targets.add(serializeRef(receivingCall));
                }
                obj.add("targets", targets);
            }
            return obj;
        }

        // Handle MOVE TO — operands are now objects {name, ref_mod_start?, ref_mod_length?}
        JsonObject obj = newStatement("MOVE");
        JsonArray operands = new JsonArray();

        MoveToStatement moveToStmt = stmt.getMoveToStatement();
        if (moveToStmt != null) {
            MoveToSendingArea sendingArea = moveToStmt.getSendingArea();
            if (sendingArea != null) {
                ValueStmt vs = sendingArea.getSendingAreaValueStmt();
                Call sourceCall = null;
                if (vs instanceof CallValueStmt) {
                    sourceCall = ((CallValueStmt) vs).getCall();
                }
                JsonObject functionNode =
                        (sourceCall != null) ? serializeFunctionNode(sourceCall) : null;
                if (functionNode == null) {
                    // ValueStmt's own ctx may carry the functionCall even when the
                    // Call does not (e.g. CURRENT-DATE with no parenthesised args).
                    functionNode = serializeFunctionNodeFromValueStmt(vs);
                }
                JsonObject lengthOfNode = serializeMoveLengthOfSource(vs);
                CobolParser.LiteralContext sendingLiteral =
                        sendingArea.getCtx() instanceof CobolParser.MoveToSendingAreaContext areaCtx
                                ? areaCtx.literal() : null;
                boolean moveAll = stmt.getCtx() instanceof CobolParser.MoveStatementContext moveCtx
                        && moveCtx.ALL() != null;
                if (moveAll && sendingLiteral != null) {
                    operands.add(moveAllSource(sendingLiteral));
                } else if (functionNode != null) {
                    operands.add(functionNode);
                } else if (lengthOfNode != null) {
                    // `MOVE LENGTH OF <field> TO ...` — emit a structured
                    // length_of node (the field's byte length) rather than a
                    // null-name literal. Mirrors serializeFromValue's handling
                    // (used by PERFORM VARYING FROM). (red-dragon)
                    operands.add(lengthOfNode);
                } else if (sourceCall != null) {
                    operands.add(serializeMoveOperand(sourceCall));
                } else if (vs instanceof LiteralValueStmt) {
                    JsonObject dfh = serializeDfhrespLit((LiteralValueStmt) vs);
                    if (dfh != null) {
                        operands.add(dfh);
                    } else {
                        JsonObject srcObj = new JsonObject();
                        srcObj.addProperty("name", extractValueStmtText(vs));
                        markNumeric(srcObj, vs);
                        operands.add(srcObj);
                    }
                } else {
                    // Complex expression source: plain name object, no ref mod
                    JsonObject srcObj = new JsonObject();
                    srcObj.addProperty("name", extractValueStmtText(vs));
                    markNumeric(srcObj, vs);
                    operands.add(srcObj);
                }
            }

            for (Call receivingCall : moveToStmt.getReceivingAreaCalls()) {
                operands.add(serializeMoveOperand(receivingCall));
            }
        }

        obj.add("operands", operands);
        return obj;
    }

    private static void addSizeErrorPhrases(
            JsonObject obj, OnSizeErrorPhrase onSizeError, NotOnSizeErrorPhrase notOnSizeError) {
        if (onSizeError != null) {
            obj.add("on_size_error", serializeStatements(onSizeError.getStatements()));
        }
        if (notOnSizeError != null) {
            obj.add("not_on_size_error", serializeStatements(notOnSizeError.getStatements()));
        }
    }

    private static JsonObject serializeAdd(AddStatement stmt) {
        // ADD CORRESPONDING src TO dst
        io.proleap.cobol.asg.metamodel.procedure.add.AddCorrespondingStatement addCorr =
            stmt.getAddCorrespondingStatement();
        if (addCorr != null) {
            JsonObject obj = newStatement("ADD_CORRESPONDING");
            obj.add("source", serializeRef(addCorr.getFromCall()));
            io.proleap.cobol.asg.metamodel.procedure.add.To corrTo = addCorr.getTo();
            if (corrTo != null) {
                JsonObject t = serializeRef(corrTo.getToCall());
                t.addProperty("rounded", corrTo.isRounded());
                obj.add("target", t);
            }
            addSizeErrorPhrases(obj, stmt.getOnSizeErrorPhrase(), stmt.getNotOnSizeErrorPhrase());
            return obj;
        }

        JsonObject obj = newStatement("ADD");
        JsonArray operands = new JsonArray();
        JsonArray targets = new JsonArray();

        AddToStatement addTo = stmt.getAddToStatement();
        if (addTo != null) {
            for (From from : addTo.getFroms()) {
                ValueStmt vs = from.getFromValueStmt();
                operands.add(serializeArithSource(vs));
            }
            for (To to : addTo.getTos()) {
                JsonObject t = serializeRef(to.getToCall());
                t.addProperty("rounded", to.isRounded());
                targets.add(t);
            }
        } else {
            AddToGivingStatement addGiving = stmt.getAddToGivingStatement();
            if (addGiving != null) {
                for (From from : addGiving.getFroms()) {
                    operands.add(serializeArithSource(from.getFromValueStmt()));
                }
                for (ToGiving to : addGiving.getTos()) {
                    operands.add(serializeArithSource(to.getToValueStmt()));
                }
                JsonArray givingTargets = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.add.Giving g : addGiving.getGivings()) {
                    JsonObject gt = serializeRef(g.getGivingCall());
                    gt.addProperty("rounded", g.isRounded());
                    givingTargets.add(gt);
                }
                if (givingTargets.size() > 0) {
                    obj.add("giving", givingTargets);
                }
            }
        }

        obj.add("operands", operands);
        if (targets.size() > 0) {
            obj.add("targets", targets);
        }
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeSubtract(SubtractStatement stmt) {
        // SUBTRACT CORRESPONDING src FROM dst
        io.proleap.cobol.asg.metamodel.procedure.subtract.SubtractCorrespondingStatement subCorr =
            stmt.getSubtractCorrespondingStatement();
        if (subCorr != null) {
            JsonObject obj = newStatement("SUBTRACT_CORRESPONDING");
            obj.add("source", serializeRef(subCorr.getSubtrahendCall()));
            io.proleap.cobol.asg.metamodel.procedure.subtract.MinuendCorresponding minCorr =
                subCorr.getMinuend();
            if (minCorr != null) {
                JsonObject t = serializeRef(minCorr.getMinuendCall());
                t.addProperty("rounded", minCorr.isRounded());
                obj.add("target", t);
            }
            addSizeErrorPhrases(obj, stmt.getOnSizeErrorPhrase(), stmt.getNotOnSizeErrorPhrase());
            return obj;
        }

        JsonObject obj = newStatement("SUBTRACT");
        JsonArray subtrahends = new JsonArray();
        JsonArray targets = new JsonArray();

        SubtractFromStatement subtractFrom = stmt.getSubtractFromStatement();
        if (subtractFrom != null) {
            for (Subtrahend sub : subtractFrom.getSubtrahends()) {
                subtrahends.add(serializeArithSource(sub.getSubtrahendValueStmt()));
            }
            for (Minuend min : subtractFrom.getMinuends()) {
                JsonObject t = serializeRef(min.getMinuendCall());
                t.addProperty("rounded", min.isRounded());
                targets.add(t);
            }
        } else {
            SubtractFromGivingStatement subtractGiving = stmt.getSubtractFromGivingStatement();
            if (subtractGiving != null) {
                for (Subtrahend sub : subtractGiving.getSubtrahends()) {
                    subtrahends.add(serializeArithSource(sub.getSubtrahendValueStmt()));
                }
                MinuendGiving minuend = subtractGiving.getMinuend();
                if (minuend != null) {
                    obj.add("minuend", serializeArithSource(minuend.getMinuendValueStmt()));
                }
                JsonArray givingTargets = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.subtract.Giving g : subtractGiving.getGivings()) {
                    JsonObject gt = serializeRef(g.getGivingCall());
                    gt.addProperty("rounded", g.isRounded());
                    givingTargets.add(gt);
                }
                if (givingTargets.size() > 0) {
                    obj.add("giving", givingTargets);
                }
            }
        }

        obj.add("subtrahends", subtrahends);
        if (targets.size() > 0) {
            obj.add("targets", targets);
        }
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeMultiply(MultiplyStatement stmt) {
        JsonObject obj = newStatement("MULTIPLY");
        JsonArray operands = new JsonArray();
        JsonArray targets = new JsonArray();
        try {
            // Source operand: the value being multiplied
            ValueStmt operandVs = stmt.getOperandValueStmt();
            if (operandVs != null) {
                operands.add(serializeArithSource(operandVs));
            }

            MultiplyStatement.MultiplyType multiplyType = stmt.getMultiplyType();

            if (multiplyType == MultiplyStatement.MultiplyType.BY_GIVING) {
                // MULTIPLY X BY Y GIVING Z
                // operand = X (source), giving_operand = Y, giving_result = Z
                io.proleap.cobol.asg.metamodel.procedure.multiply.GivingPhrase givingPhrase = stmt.getGivingPhrase();
                if (givingPhrase != null) {
                    io.proleap.cobol.asg.metamodel.procedure.multiply.GivingOperand givingOp = givingPhrase.getGivingOperand();
                    if (givingOp != null && givingOp.getOperandValueStmt() != null) {
                        operands.add(serializeArithSource(givingOp.getOperandValueStmt()));
                    }
                    // GIVING targets
                    JsonArray givingTargets = new JsonArray();
                    for (io.proleap.cobol.asg.metamodel.procedure.multiply.GivingResult gr : givingPhrase.getGivingResults()) {
                        Call resultCall = gr.getResultCall();
                        if (resultCall != null) {
                            JsonObject gt = serializeRef(resultCall);
                            gt.addProperty("rounded", gr.isRounded());
                            givingTargets.add(gt);
                        }
                    }
                    if (givingTargets.size() > 0) {
                        obj.add("giving", givingTargets);
                    }
                }
            } else {
                // MULTIPLY X BY Y (in-place: Y = Y * X)
                io.proleap.cobol.asg.metamodel.procedure.multiply.ByPhrase byPhrase = stmt.getByPhrase();
                if (byPhrase != null) {
                    for (ByOperand byOp : byPhrase.getByOperands()) {
                        Call targetCall = byOp.getOperandCall();
                        if (targetCall != null) {
                            JsonObject t = serializeRef(targetCall);
                            t.addProperty("rounded", byOp.isRounded());
                            targets.add(t);
                        }
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract MULTIPLY operands: " + e.getMessage());
        }
        obj.add("operands", operands);
        if (targets.size() > 0) {
            obj.add("targets", targets);
        }
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeDivide(DivideStatement stmt) {
        JsonObject obj = newStatement("DIVIDE");
        JsonArray targets = new JsonArray();
        try {
            ValueStmt operandVs = stmt.getOperandValueStmt();

            Remainder remainder = stmt.getRemainder();
            if (remainder != null && remainder.getRemainderCall() != null) {
                obj.add("remainder", serializeRef(remainder.getRemainderCall()));
            }

            DivideStatement.DivideType divideType = stmt.getDivideType();

            if (divideType == DivideStatement.DivideType.INTO_GIVING) {
                DivideIntoGivingStatement intoGiving = stmt.getDivideIntoGivingStatement();
                if (operandVs != null) {
                    obj.add("divisor", serializeArithSource(operandVs));
                }
                if (intoGiving != null) {
                    if (intoGiving.getIntoValueStmt() != null) {
                        obj.add("dividend", serializeArithSource(intoGiving.getIntoValueStmt()));
                    }
                    addDivideGiving(obj, intoGiving.getGivingPhrase());
                }
            } else if (divideType == DivideStatement.DivideType.BY_GIVING) {
                DivideByGivingStatement byGiving = stmt.getDivideByGivingStatement();
                if (operandVs != null) {
                    obj.add("dividend", serializeArithSource(operandVs));
                }
                if (byGiving != null) {
                    if (byGiving.getByValueStmt() != null) {
                        obj.add("divisor", serializeArithSource(byGiving.getByValueStmt()));
                    }
                    addDivideGiving(obj, byGiving.getGivingPhrase());
                }
            } else {
                DivideIntoStatement intoStmt = stmt.getDivideIntoStatement();
                if (operandVs != null) {
                    obj.add("divisor", serializeArithSource(operandVs));
                }
                if (intoStmt != null) {
                    for (Into into : intoStmt.getIntos()) {
                        Call targetCall = into.getGivingCall();
                        if (targetCall != null) {
                            JsonObject t = serializeRef(targetCall);
                            t.addProperty("rounded", into.isRounded());
                            targets.add(t);
                        }
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DIVIDE operands: " + e.getMessage());
        }
        if (targets.size() > 0) {
            obj.add("targets", targets);
        }
        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static void addDivideGiving(JsonObject obj, GivingPhrase gp) {
        if (gp == null) {
            return;
        }
        JsonArray givingTargets = new JsonArray();
        for (Giving g : gp.getGivings()) {
            Call givingCall = g.getGivingCall();
            if (givingCall != null) {
                JsonObject gt = serializeRef(givingCall);
                gt.addProperty("rounded", g.isRounded());
                givingTargets.add(gt);
            }
        }
        if (givingTargets.size() > 0) {
            obj.add("giving", givingTargets);
        }
    }

    private static JsonObject serializeCompute(ComputeStatement stmt) {
        JsonObject obj = newStatement("COMPUTE");

        // Extract arithmetic expression using structured AST
        if (stmt.getArithmeticExpression() != null) {
            obj.add("expression", serializeArithmeticExpr(stmt.getArithmeticExpression()));
        }

        // Extract target variables
        JsonArray targets = new JsonArray();
        for (Store store : stmt.getStores()) {
            Call storeCall = store.getStoreCall();
            if (storeCall != null) {
                JsonObject t = serializeRef(storeCall);
                t.addProperty("rounded", store.isRounded());
                targets.add(t);
            }
        }

        if (targets.size() > 0) {
            obj.add("targets", targets);
        }

        if (stmt.getOnSizeErrorPhrase() != null) {
            obj.add("on_size_error", serializeStatements(
                stmt.getOnSizeErrorPhrase().getStatements()));
        }
        if (stmt.getNotOnSizeErrorPhrase() != null) {
            obj.add("not_on_size_error", serializeStatements(
                stmt.getNotOnSizeErrorPhrase().getStatements()));
        }
        return obj;
    }

    private static JsonObject serializeIf(IfStatement stmt) {
        JsonObject obj = newStatement("IF");

        try {
            if (stmt.getCondition() != null) {
                obj.add("condition", serializeConditionNode(stmt.getCondition()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract IF condition: " + e.getMessage());
        }

        JsonArray children = new JsonArray();
        Then thenBlock = stmt.getThen();
        if (thenBlock != null && thenBlock.isNextSentence()) {
            children.add(nextSentence(thenBlock.getCtx()));
        } else if (thenBlock != null && thenBlock.getStatements() != null) {
            children = serializeStatements(thenBlock.getStatements());
        }
        if (children.size() > 0) {
            obj.add("children", children);
        }

        JsonArray elseChildren = new JsonArray();
        Else elseBlock = stmt.getElse();
        if (elseBlock != null && elseBlock.isNextSentence()) {
            elseChildren.add(nextSentence(elseBlock.getCtx()));
        } else if (elseBlock != null && elseBlock.getStatements() != null) {
            elseChildren = serializeStatements(elseBlock.getStatements());
        }
        if (elseChildren.size() > 0) {
            obj.add("else_children", elseChildren);
        }

        return obj;
    }

    private static JsonObject serializePerform(PerformStatement stmt) {
        JsonObject obj = newStatement("PERFORM");
        JsonArray operands = new JsonArray();

        PerformProcedureStatement procStmt = stmt.getPerformProcedureStatement();
        if (procStmt != null) {
            List<Call> calls = procStmt.getCalls();
            if (!calls.isEmpty()) {
                // First call is the start paragraph
                operands.add(extractCallName(calls.get(0)));
                addProcedureSection(obj, "target_section", calls.get(0));
            }
            // If there are >= 2 calls, last call is the THRU paragraph
            if (calls.size() >= 2) {
                Call thru = calls.get(calls.size() - 1);
                obj.addProperty("thru", extractCallName(thru));
                addProcedureSection(obj, "thru_section", thru);
            }
            serializePerformType(procStmt.getPerformType(), obj);
        }

        if (operands.size() > 0) {
            obj.add("operands", operands);
        }

        PerformInlineStatement inlineStmt = stmt.getPerformInlineStatement();
        if (inlineStmt != null) {
            serializePerformType(inlineStmt.getPerformType(), obj);
            if (inlineStmt.getStatements() != null) {
                JsonArray children = serializeStatements(inlineStmt.getStatements());
                if (children.size() > 0) {
                    obj.add("children", children);
                }
            }
        }

        return obj;
    }

    /**
     * Serializes PerformType (TIMES / UNTIL / VARYING) fields into the statement JSON.
     */
    private static void serializePerformType(PerformType pt, JsonObject obj) {
        if (pt == null) {
            return;
        }

        try {
            PerformType.PerformTypeType typeType = pt.getPerformTypeType();
            if (typeType == null) {
                return;
            }

            if (typeType == PerformType.PerformTypeType.TIMES) {
                obj.addProperty("perform_type", "TIMES");
                Times times = pt.getTimes();
                if (times != null && times.getTimesValueStmt() != null) {
                    obj.add("times", serializeFromValue(times.getTimesValueStmt()));
                }
            } else if (typeType == PerformType.PerformTypeType.UNTIL) {
                obj.addProperty("perform_type", "UNTIL");
                Until until = pt.getUntil();
                if (until != null) {
                    serializeUntilFields(until, obj);
                }
                serializeTestClause(pt, obj);
            } else if (typeType == PerformType.PerformTypeType.VARYING) {
                obj.addProperty("perform_type", "VARYING");
                Varying varying = pt.getVarying();
                if (varying != null) {
                    VaryingClause vc = varying.getVaryingClause();
                    if (vc != null && vc.getVaryingPhrase() != null) {
                        VaryingPhrase vp = vc.getVaryingPhrase();
                        if (vp.getVaryingValueStmt() != null) {
                            obj.add("varying_var", serializeFromValue(vp.getVaryingValueStmt()));
                        }
                        if (vp.getFrom() != null && vp.getFrom().getFromValueStmt() != null) {
                            obj.add("varying_from", serializeFromValue(vp.getFrom().getFromValueStmt()));
                        }
                        if (vp.getBy() != null && vp.getBy().getByValueStmt() != null) {
                            obj.add("varying_by", serializeFromValue(vp.getBy().getByValueStmt()));
                        }
                        if (vp.getUntil() != null) {
                            serializeUntilFields(vp.getUntil(), obj);
                        }
                    }
                    List<After> afters = vc.getAfters();
                    if (afters != null && !afters.isEmpty()) {
                        JsonArray afterArr = new JsonArray();
                        for (After after : afters) {
                            if (after == null) continue;
                            VaryingPhrase ap = after.getVaryingPhrase();
                            if (ap == null) continue;
                            JsonObject aObj = new JsonObject();
                            if (ap.getVaryingValueStmt() != null) {
                                aObj.add("varying_var",
                                    serializeFromValue(ap.getVaryingValueStmt()));
                            }
                            if (ap.getFrom() != null && ap.getFrom().getFromValueStmt() != null) {
                                aObj.add("varying_from",
                                    serializeFromValue(ap.getFrom().getFromValueStmt()));
                            }
                            if (ap.getBy() != null && ap.getBy().getByValueStmt() != null) {
                                aObj.add("varying_by",
                                    serializeFromValue(ap.getBy().getByValueStmt()));
                            }
                            if (ap.getUntil() != null) {
                                serializeUntilFields(ap.getUntil(), aObj);
                            }
                            afterArr.add(aObj);
                        }
                        if (afterArr.size() > 0) {
                            obj.add("after_specs", afterArr);
                        }
                    }
                }
                serializeTestClause(pt, obj);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract PerformType: " + e.getMessage());
        }
    }

    /**
     * Serializes Until condition fields into the JSON object.
     */
    private static void serializeUntilFields(Until until, JsonObject obj) {
        if (until.getCondition() != null) {
            try {
                obj.add("until", serializeConditionNode(until.getCondition()));
            } catch (Exception e) {
                LOG.fine("Could not serialize UNTIL condition: " + e.getMessage());
            }
        }
    }

    /**
     * Serializes test clause (TEST BEFORE / TEST AFTER) from a PerformType.
     */
    private static void serializeTestClause(PerformType pt, JsonObject obj) {
        try {
            // Check until's test clause first, then varying's
            Until until = pt.getUntil();
            TestClause tc = null;
            if (until != null) {
                tc = until.getTestClause();
            }
            if (tc == null) {
                Varying varying = pt.getVarying();
                if (varying != null) {
                    tc = varying.getTestClause();
                }
            }
            if (tc != null && tc.getTestClauseType() != null) {
                boolean testBefore = (tc.getTestClauseType() == TestClause.TestClauseType.BEFORE);
                obj.addProperty("test_before", testBefore);
            } else {
                obj.addProperty("test_before", true); // COBOL default: TEST BEFORE
            }
        } catch (Exception e) {
            obj.addProperty("test_before", true);
        }
    }

    private static JsonObject serializeDisplay(DisplayStatement stmt) {
        JsonObject obj = newStatement("DISPLAY");
        JsonArray operands = new JsonArray();

        for (Operand operand : stmt.getOperands()) {
            ValueStmt vs = operand.getOperandValueStmt();
            if (vs instanceof CallValueStmt) {
                operands.add(serializeMoveOperand(((CallValueStmt) vs).getCall()));
            } else {
                JsonObject literalObj = new JsonObject();
                literalObj.addProperty("name", extractValueStmtText(vs));
                markNumeric(literalObj, vs);
                operands.add(literalObj);
            }
        }

        obj.add("operands", operands);
        if (stmt.getWith() != null && stmt.getWith().isNoAdvancing()) {
            obj.addProperty("no_advancing", true);
        }
        return obj;
    }

    private static JsonObject serializeStop(StopStatement stmt) {
        return newStatement("STOP_RUN");
    }

    private static JsonObject serializeGoTo(GoToStatement stmt) {
        JsonObject obj = newStatement("GOTO");
        try {
            if (stmt.getGoToType() == GoToStatement.GoToType.DEPENDING_ON) {
                obj.addProperty("form", "computed");
                DependingOnPhrase dep = stmt.getDependingOnPhrase();
                JsonArray targets = new JsonArray();
                for (Call c : dep.getProcedureCalls()) {
                    targets.add(serializeProcedureRef(c));
                }
                obj.add("targets", targets);
                obj.add("index", serializeRef(dep.getDependingOnCall()));
            } else if (stmt.getSimple() != null
                    && stmt.getSimple().getProcedureCall() != null) {
                obj.addProperty("form", "simple");
                obj.add("target", serializeProcedureRef(stmt.getSimple().getProcedureCall()));
            } else {
                obj.addProperty("form", "altered");
            }
        } catch (Exception e) {
            LOG.fine("Could not extract GOTO: " + e.getMessage());
            obj.addProperty("form", "altered");
        }
        return obj;
    }

    private static JsonObject serializeProcedureRef(Call call) {
        JsonObject obj = new JsonObject();
        obj.addProperty("paragraph", extractCallName(call));
        obj.addProperty("section", procedureSection(call));
        return obj;
    }

    static void addProcedureSection(JsonObject obj, String property, Call call) {
        String section = procedureSection(call);
        if (!section.isEmpty()) {
            obj.addProperty(property, section);
        }
    }

    /** The section named by a procedure-name's {@code OF}/{@code IN} qualifier, or "". */
    private static String procedureSection(Call call) {
        if (call == null || !(call.unwrap() instanceof ASGElementImpl element)) {
            return "";
        }
        if (!(element.getCtx() instanceof CobolParser.ProcedureNameContext name)
                || name.inSection() == null) {
            return "";
        }
        return name.inSection().sectionName().getText();
    }

    private static JsonObject serializeEvaluate(EvaluateStatement stmt) {
        JsonObject obj = newStatement("EVALUATE");
        JsonArray subjects = new JsonArray();
        subjects.add(serializeSelectionSubject(stmt.getSelect().getSelectValueStmt()));
        for (AlsoSelect alsoSelect : stmt.getAlsoSelects()) {
            subjects.add(serializeSelectionSubject(alsoSelect.getSelect().getSelectValueStmt()));
        }
        obj.add("subjects", subjects);

        JsonArray children = new JsonArray();
        // Each WhenPhrase is "WHEN c1 [WHEN c2 ...] statements": one or more
        // stacked WHENs sharing a single body. Emit ONE WHEN per phrase: the
        // first WHEN's objects on the WHEN itself, the rest as body-less WHENs
        // under "alternatives", and the body once.
        for (WhenPhrase whenPhrase : stmt.getWhenPhrases()) {
            JsonObject phraseObj = null;
            JsonArray alternatives = new JsonArray();
            for (io.proleap.cobol.asg.metamodel.procedure.evaluate.When when : whenPhrase.getWhens()) {
                JsonObject whenObj = newStatement("WHEN");
                JsonArray objects = new JsonArray();
                objects.add(serializeSelectionObject(when.getCondition()));
                for (AlsoCondition alsoCond : when.getAlsoConditions()) {
                    objects.add(serializeSelectionObject(alsoCond.getCondition()));
                }
                whenObj.add("objects", objects);
                if (phraseObj == null) {
                    phraseObj = whenObj;
                } else {
                    alternatives.add(whenObj);
                }
            }
            if (phraseObj == null) {
                continue;
            }
            if (alternatives.size() > 0) {
                phraseObj.add("alternatives", alternatives);
            }
            JsonArray whenStmts = serializeStatements(whenPhrase.getStatements());
            if (whenStmts.size() > 0) phraseObj.add("children", whenStmts);
            children.add(phraseObj);
        }

        io.proleap.cobol.asg.metamodel.procedure.evaluate.WhenOther whenOther = stmt.getWhenOther();
        if (whenOther != null && whenOther.getStatements() != null && !whenOther.getStatements().isEmpty()) {
            JsonObject whenOtherObj = newStatement("WHEN_OTHER");
            JsonArray otherStmts = serializeStatements(whenOther.getStatements());
            if (otherStmts.size() > 0) {
                whenOtherObj.add("children", otherStmts);
            }
            children.add(whenOtherObj);
        }

        if (children.size() > 0) {
            obj.add("children", children);
        }
        return obj;
    }

    /**
     * An EVALUATE selection subject: a truth value (TRUE / FALSE), a
     * condition, or an identifier / literal / arithmetic expression, each kept
     * structured so a subscript, a qualifier, a slice or an operator survives.
     */
    private static JsonObject serializeSelectionSubject(ValueStmt vs) {
        JsonObject subject = new JsonObject();
        if (vs instanceof ConditionValueStmt) {
            subject.addProperty("kind", "condition");
            subject.add("condition", serializeConditionNode((ConditionValueStmt) vs));
            return subject;
        }
        JsonObject conditionName = conditionNameOf(vs, false);
        if (conditionName != null) {
            subject.addProperty("kind", "condition");
            subject.add("condition", conditionName);
            return subject;
        }
        CobolParser.BooleanLiteralContext truth = booleanLiteralOf(vs.getCtx());
        if (truth != null) {
            subject.addProperty("kind", "boolean");
            subject.addProperty("value", truth.TRUE() != null);
            return subject;
        }
        subject.addProperty("kind", "expr");
        subject.add("expr", serializeFromValue(vs));
        return subject;
    }

    /**
     * An EVALUATE selection object: ANY, a truth value, a condition, or a
     * [NOT] value [THRU value] whose operands are structured expressions.
     */
    private static JsonObject serializeSelectionObject(
            io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition cond) {
        JsonObject object = new JsonObject();
        io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType ct = cond.getConditionType();
        if (ct == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.ANY) {
            object.addProperty("kind", "any");
            return object;
        }
        if (ct == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.CONDITION) {
            object.addProperty("kind", "condition");
            object.add("condition", serializeConditionNode((ConditionValueStmt) cond.getConditionValueStmt()));
            return object;
        }
        if (ct == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.BOOLEAN) {
            object.addProperty("kind", "boolean");
            object.addProperty("value", booleanLiteralOf(cond.getConditionValueStmt().getCtx()).TRUE() != null);
            return object;
        }
        ValueStmt value = cond.getValue().getValueStmt();
        CobolParser.BooleanLiteralContext truth = booleanLiteralOf(value.getCtx());
        if (truth != null) {
            object.addProperty("kind", "boolean");
            object.addProperty("value", (truth.TRUE() != null) != cond.isNot());
            return object;
        }
        JsonObject conditionName = conditionNameOf(value, cond.isNot());
        if (conditionName != null) {
            object.addProperty("kind", "condition");
            object.add("condition", conditionName);
            return object;
        }
        object.addProperty("not", cond.isNot());
        if (ct == io.proleap.cobol.asg.metamodel.procedure.evaluate.Condition.ConditionType.VALUE_THROUGH) {
            object.addProperty("kind", "range");
            object.add("from", serializeSelectionValue(value));
            object.add("thru", serializeSelectionValue(cond.getThrough().getValue().getValueStmt()));
            return object;
        }
        object.addProperty("kind", "value");
        object.add("value", serializeSelectionValue(value));
        return object;
    }

    /** A selection value: DFHRESP(x) as its own node, anything else as an expression. */
    private static JsonElement serializeSelectionValue(ValueStmt vs) {
        JsonObject dfh = serializeDfhrespFromVS(vs);
        return dfh != null ? dfh : serializeFromValue(vs);
    }

    /**
     * An identifier naming a condition-name (a level-88 entry) is that
     * condition, wherever an EVALUATE subject or object stands: the grammar
     * reads it as an identifier, so only name resolution tells the two apart.
     * Null for any other value.
     */
    private static JsonObject conditionNameOf(ValueStmt vs, boolean not) {
        if (!(vs instanceof CallValueStmt)) {
            return null;
        }
        Call call = ((CallValueStmt) vs).getCall();
        if (!(call.unwrap() instanceof DataDescriptionEntryCall entryCall)
                || !(entryCall.getDataDescriptionEntry() instanceof DataDescriptionEntryCondition)) {
            return null;
        }
        JsonObject condition = new JsonObject();
        condition.addProperty("not", not);
        condition.addProperty("condition_name", extractCallName(call));
        JsonArray subscripts = extractSubscripts(call);
        if (subscripts.size() > 0) {
            condition.add("condition_subscripts", subscripts);
        }
        JsonArray qualifiers = new JsonArray();
        collectInDataQualifiers(vs.getCtx(), qualifiers);
        if (qualifiers.size() > 0) {
            condition.add("condition_qualifiers", qualifiers);
        }
        return condition;
    }

    /**
     * Whether ProLeap resolves a name written where a condition stands to a data
     * item rather than to a level-88 entry: {@code IF A = 1 OR B} with B a data
     * item, an abbreviated operand. Switch condition-names do not resolve to a
     * data description entry, so they stay condition names.
     */
    private static boolean namesDataItem(Call call) {
        return call != null
                && call.unwrap() instanceof DataDescriptionEntryCall entryCall
                && !(entryCall.getDataDescriptionEntry() instanceof DataDescriptionEntryCondition);
    }

    /** The data item a condition-name reference resolved to, as a reference operand. */
    private static JsonObject dataOperand(ConditionNameReference ref) {
        JsonObject operand = new JsonObject();
        operand.addProperty("kind", "ref");
        operand.addProperty("name", extractCallName(ref.getConditionCall()));
        JsonArray subscripts = extractConditionSubscripts(ref);
        if (subscripts.size() > 0) {
            operand.add("subscripts", subscripts);
        }
        JsonArray qualifiers = new JsonArray();
        collectInDataQualifiers(ref.getCtx(), qualifiers);
        if (qualifiers.size() > 0) {
            operand.add("qualifiers", qualifiers);
        }
        return operand;
    }

    /** The TRUE / FALSE literal a context consists of, or null when it is anything else. */
    private static CobolParser.BooleanLiteralContext booleanLiteralOf(ParserRuleContext ctx) {
        if (ctx instanceof CobolParser.BooleanLiteralContext) {
            return (CobolParser.BooleanLiteralContext) ctx;
        }
        if (ctx instanceof CobolParser.LiteralContext) {
            return ((CobolParser.LiteralContext) ctx).booleanLiteral();
        }
        return null;
    }

    private static JsonObject serializeContinue(ContinueStatement stmt) {
        return newStatement("CONTINUE");
    }

    private static JsonObject serializeExit(ExitStatement stmt) {
        // EXIT PROGRAM returns to the caller and is its own statement. Every other
        // EXIT is one statement with a kind saying which construct it leaves; a
        // plain paragraph-end EXIT carries none and serialises as before.
        ExitStatement.ExitStatementType type = stmt.getExitStatementType();
        if (type == ExitStatement.ExitStatementType.PROGRAM) {
            return newStatement("EXIT_PROGRAM");
        }
        JsonObject result = newStatement("EXIT");
        String kind = exitKind(type);
        if (!kind.isEmpty()) {
            result.addProperty("kind", kind);
        }
        return result;
    }

    private static String exitKind(ExitStatement.ExitStatementType type) {
        if (type == null) {
            return "";
        }
        switch (type) {
            case PARAGRAPH: return "paragraph";
            case SECTION: return "section";
            case PERFORM: return "perform";
            case PERFORM_CYCLE: return "perform-cycle";
            default: return "";
        }
    }

    private static JsonObject serializeGoback(GobackStatement stmt) {
        return newStatement("GOBACK");
    }

    private static JsonObject serializeInitialize(InitializeStatement stmt) {
        JsonObject obj = newStatement("INITIALIZE");
        JsonArray operands = new JsonArray();
        for (Call dataItemCall : stmt.getDataItemCalls()) {
            operands.add(serializeMoveOperand(dataItemCall));
        }
        obj.add("operands", operands);
        JsonArray replacing = new JsonArray();
        if (stmt.getReplacingPhrase() != null) {
            for (By by : stmt.getReplacingPhrase().getBys()) {
                JsonObject phrase = new JsonObject();
                phrase.addProperty("category", by.getByType().name());
                phrase.add("by", serializeReplacingValue(by.getValueStmt()));
                replacing.add(phrase);
            }
        }
        obj.add("replacing", replacing);
        return obj;
    }

    private static JsonObject serializeReplacingValue(ValueStmt vs) {
        if (vs instanceof CallValueStmt callValue) {
            return serializeMoveOperand(callValue.getCall());
        }
        JsonObject literal = new JsonObject();
        literal.addProperty("name", extractValueStmtText(vs));
        markNumeric(literal, vs);
        return literal;
    }

    private static JsonObject serializeSet(SetStatement stmt) {
        JsonObject obj = newStatement("SET");
        try {
            SetStatement.SetType setType = stmt.getSetType();
            if (setType == SetStatement.SetType.TO) {
                obj.addProperty("set_type", "TO");
                JsonArray targets = new JsonArray();
                JsonArray values = new JsonArray();
                // One value per target: each target takes the value of its own
                // TO phrase, as in SET A TO 1 B TO 2.
                for (SetTo setTo : stmt.getSetTos()) {
                    JsonObject value = setToValueOperand(setTo.getValues().get(0));
                    for (io.proleap.cobol.asg.metamodel.procedure.set.To to : setTo.getTos()) {
                        targets.add(callOperand(to.getToCall()));
                        values.add(value.deepCopy());
                    }
                }
                obj.add("targets", targets);
                obj.add("values", values);
            } else if (setType == SetStatement.SetType.BY) {
                obj.addProperty("set_type", "BY");
                SetBy setBy = stmt.getSetBy();
                if (setBy != null) {
                    String byType = (setBy.getSetByType() == SetBy.SetByType.UP) ? "UP" : "DOWN";
                    obj.addProperty("by_type", byType);
                    JsonArray targets = new JsonArray();
                    for (io.proleap.cobol.asg.metamodel.procedure.set.To to : setBy.getTos()) {
                        targets.add(callOperand(to.getToCall()));
                    }
                    obj.add("targets", targets);
                    if (setBy.getBy() != null && setBy.getBy().getByValueStmt() != null) {
                        obj.add("value", setValueOperand(setBy.getBy().getByValueStmt()));
                    }
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract SET operands: " + e.getMessage());
        }
        return obj;
    }

    /** The identifier an ADDRESS OF special register names, or null for any other call. */
    private static Call addressOfTarget(Call call) {
        if (call == null) return null;
        Call unwrapped = call.unwrap();
        if (unwrapped instanceof SpecialRegisterCall sr
                && sr.getSpecialRegisterType() == SpecialRegisterCall.SpecialRegisterType.ADDRESS_OF) {
            return sr.getIdentifierCall();
        }
        return null;
    }

    /** A reference operand of the given kind, its qualifiers and subscripts always present. */
    private static JsonObject operandRef(Call call, String kind) {
        JsonObject ref = serializeRef(call);
        JsonObject node = new JsonObject();
        node.addProperty("kind", kind);
        node.add("name", ref.get("name"));
        node.add("qualifiers", ref.has("qualifiers") ? ref.get("qualifiers") : new JsonArray());
        node.add("subscripts", ref.has("subscripts") ? ref.get("subscripts") : new JsonArray());
        return node;
    }

    /** A data reference, the item an ADDRESS OF names, or the item a LENGTH OF measures. */
    private static JsonObject callOperand(Call call) {
        Call target = addressOfTarget(call);
        if (target != null) {
            return operandRef(target, "address_of");
        }
        Call measured = lengthOfTarget(call);
        return measured != null ? operandRef(measured, "length_of") : operandRef(call, "ref");
    }

    /** The identifier a LENGTH OF special register names, or null for any other call. */
    private static Call lengthOfTarget(Call call) {
        if (call == null) return null;
        Call unwrapped = call.unwrap();
        if (unwrapped instanceof SpecialRegisterCall sr
                && sr.getSpecialRegisterType() == SpecialRegisterCall.SpecialRegisterType.LENGTH_OF) {
            return sr.getIdentifierCall();
        }
        return null;
    }

    /** A SET value: a reference, ADDRESS OF, a figurative constant (NULL among them) or a literal. */
    /** A SET ... TO value: ON or OFF for an implementor switch, else the value's operand. */
    private static JsonObject setToValueOperand(io.proleap.cobol.asg.metamodel.procedure.set.Value val) {
        io.proleap.cobol.asg.metamodel.procedure.set.Value.ValueType type = val.getValueType();
        if (type == io.proleap.cobol.asg.metamodel.procedure.set.Value.ValueType.ON
                || type == io.proleap.cobol.asg.metamodel.procedure.set.Value.ValueType.OFF) {
            JsonObject status = new JsonObject();
            status.addProperty("kind", "switch_status");
            status.addProperty("value", type.name());
            return status;
        }
        return setValueOperand(val.getValueStmt());
    }

    private static JsonObject setValueOperand(ValueStmt vs) {
        if (vs instanceof CallValueStmt && ((CallValueStmt) vs).getCall() != null) {
            return callOperand(((CallValueStmt) vs).getCall());
        }
        if (vs instanceof LiteralValueStmt) {
            Literal lit = ((LiteralValueStmt) vs).getLiteral();
            if (lit != null && lit.getLiteralType() == Literal.LiteralType.FIGURATIVE_CONSTANT
                    && lit.getFigurativeConstant() != null) {
                String canonical = canonicalFigurative(lit.getFigurativeConstant().getFigurativeConstantType());
                if (canonical != null) {
                    JsonObject fig = new JsonObject();
                    fig.addProperty("kind", "figurative");
                    fig.addProperty("value", canonical);
                    return fig;
                }
            }
        }
        return litNode(extractValueStmtText(vs), vs.getCtx());
    }

    /** The item named by a CALL USING ... ADDRESS OF operand, as a structured reference. */
    private static JsonObject addressOfOperand(ValueStmt vs) {
        if (vs instanceof CallValueStmt && ((CallValueStmt) vs).getCall() != null) {
            Call call = ((CallValueStmt) vs).getCall();
            Call target = addressOfTarget(call);
            return serializeRef(target != null ? target : call);
        }
        return textOperand(vs);
    }

    /** A CALL USING argument: a data reference with its qualifiers and subscripts, or a literal's text. */
    private static JsonObject usingOperand(ValueStmt vs) {
        if (vs instanceof CallValueStmt && ((CallValueStmt) vs).getCall() != null) {
            return serializeRef(((CallValueStmt) vs).getCall());
        }
        return textOperand(vs);
    }

    private static JsonObject textOperand(ValueStmt vs) {
        JsonObject text = new JsonObject();
        text.addProperty("name", extractValueStmtText(vs));
        markNumeric(text, vs);
        return text;
    }

    /** Copies a USING operand's name, qualifiers and subscripts onto its parameter object. */
    private static void addUsingOperand(JsonObject paramObj, JsonObject operand) {
        for (String key : new String[] {"name", "qualifiers", "subscripts"}) {
            if (operand.has(key)) {
                paramObj.add(key, operand.get(key));
            }
        }
    }

    private static JsonObject serializeString(StringStatement stmt) {
        JsonObject obj = newStatement("STRING");
        try {
            JsonArray sendings = new JsonArray();
            for (Sendings sending : stmt.getSendings()) {
                // One Sendings group may list several source operands sharing the
                // same DELIMITED BY phrase, e.g. STRING A B(1:2) DELIMITED BY SIZE.
                // Each operand must produce its own sending entry — taking only the
                // first dropped the rest (red-dragon-zuhj).
                // DELIMITED BY SIZE leaves "delimiter" out; any other delimiter is an
                // operand, a data reference keeping its subscripts (red-dragon-sl30.41).
                DelimitedByPhrase dbp = sending.getDelimitedByPhrase();
                JsonObject delim = null;
                if (dbp != null
                        && dbp.getDelimitedByType() != DelimitedByPhrase.DelimitedByType.SIZE
                        && dbp.getCharactersValueStmt() != null) {
                    delim = inspectOperand(dbp.getCharactersValueStmt());
                }
                for (ValueStmt vs : sending.getSendingValueStmts()) {
                    JsonObject sendingObj = new JsonObject();
                    if (vs instanceof CallValueStmt) {
                        Call sendingCall = ((CallValueStmt) vs).getCall();
                        // A sending operand may itself be an intrinsic FUNCTION call,
                        // e.g. STRING FUNCTION TRIM(WS-VAR) ' ...' INTO WS-MSG. Serialize
                        // it structurally (function node) so the call is evaluated, not
                        // mistaken for a literal named "TRIM" (red-dragon-zuhj).
                        JsonObject fn = serializeFunctionNode(sendingCall);
                        sendingObj.add("value",
                                (fn != null) ? fn : serializeMoveOperand(sendingCall));
                    } else {
                        JsonObject litObj = new JsonObject();
                        litObj.addProperty("name", extractValueStmtText(vs));
                        markNumeric(litObj, vs);
                        sendingObj.add("value", litObj);
                    }
                    if (delim != null) {
                        sendingObj.add("delimiter", delim);
                    }
                    sendings.add(sendingObj);
                }
            }
            obj.add("sendings", sendings);
            // Structured ref (name + ref_mod_start/length + subscripts +
            // qualifiers), not a plain name, so INTO dest(start:length)
            // reference modification on the receiving field is preserved
            // (red-dragon-2fxq) — same serializeRef already used for MOVE's
            // own receiving-field ref-mod.
            if (stmt.getIntoPhrase() != null && stmt.getIntoPhrase().getIntoCall() != null) {
                obj.add("into", serializeRef(stmt.getIntoPhrase().getIntoCall()));
            }
            // WITH POINTER (red-dragon-4q25.15)
            if (stmt.getWithPointerPhrase() != null
                    && stmt.getWithPointerPhrase().getPointerCall() != null) {
                obj.add("pointer",
                        serializeRef(stmt.getWithPointerPhrase().getPointerCall()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract STRING operands: " + e.getMessage());
        }
        addPhrase(obj, "on_overflow", stmt.getOnOverflowPhrase());
        addPhrase(obj, "not_on_overflow", stmt.getNotOnOverflowPhrase());
        return obj;
    }

    private static JsonObject serializeUnstring(UnstringStatement stmt) {
        JsonObject obj = newStatement("UNSTRING");
        try {
            if (stmt.getSending() != null && stmt.getSending().getSendingCall() != null) {
                obj.add("source", serializeMoveOperand(stmt.getSending().getSendingCall()));
            }
            // Delimiters: the DELIMITED BY operand, then each OR operand, in the
            // order written, each with its ALL flag. A delimiter is an operand: a
            // data reference keeping its qualifiers and subscripts, or a literal /
            // figurative constant (red-dragon-sl30.42).
            if (stmt.getSending() != null) {
                JsonArray delimiters = new JsonArray();
                io.proleap.cobol.asg.metamodel.procedure.unstring.DelimitedByPhrase dbp =
                        stmt.getSending().getDelimitedByPhrase();
                if (dbp != null && dbp.getDelimitedByValueStmt() != null) {
                    boolean all = ((CobolParser.UnstringDelimitedByPhraseContext) dbp.getCtx()).ALL() != null;
                    delimiters.add(unstringDelimiter(dbp.getDelimitedByValueStmt(), all));
                }
                for (io.proleap.cobol.asg.metamodel.procedure.unstring.OrAll orAll
                        : stmt.getSending().getOrAlls()) {
                    if (orAll.getOrAllValueStmt() != null) {
                        boolean all = ((CobolParser.UnstringOrAllPhraseContext) orAll.getCtx()).ALL() != null;
                        delimiters.add(unstringDelimiter(orAll.getOrAllValueStmt(), all));
                    }
                }
                obj.add("delimiters", delimiters);
            }
            // INTO receivers: each a structured ref (so INTO dest(start:length) is
            // preserved, red-dragon-2fxq) with its DELIMITER IN and COUNT IN items.
            if (stmt.getIntoPhrase() != null) {
                JsonArray intoArr = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.unstring.Into into : stmt.getIntoPhrase().getIntos()) {
                    if (into.getIntoCall() != null) {
                        JsonObject receiver = new JsonObject();
                        receiver.add("target", serializeRef(into.getIntoCall()));
                        if (into.getDelimiterIn() != null && into.getDelimiterIn().getDelimiterInCall() != null) {
                            receiver.add("delimiter_in", serializeRef(into.getDelimiterIn().getDelimiterInCall()));
                        }
                        if (into.getCountIn() != null && into.getCountIn().getCountInCall() != null) {
                            receiver.add("count_in", serializeRef(into.getCountIn().getCountInCall()));
                        }
                        intoArr.add(receiver);
                    }
                }
                obj.add("into", intoArr);
            }
            // WITH POINTER (red-dragon-4q25.15)
            if (stmt.getWithPointerPhrase() != null
                    && stmt.getWithPointerPhrase().getPointerCall() != null) {
                obj.add("pointer",
                        serializeRef(stmt.getWithPointerPhrase().getPointerCall()));
            }
            // TALLYING IN (red-dragon-4q25.14)
            if (stmt.getTallyingPhrase() != null
                    && stmt.getTallyingPhrase().getTallyCountDataItemCall() != null) {
                obj.add("tallying_target",
                        serializeRef(stmt.getTallyingPhrase().getTallyCountDataItemCall()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract UNSTRING operands: " + e.getMessage());
        }
        addPhrase(obj, "on_overflow", stmt.getOnOverflowPhrase());
        addPhrase(obj, "not_on_overflow", stmt.getNotOnOverflowPhrase());
        return obj;
    }

    /** One UNSTRING delimiter: its operand and whether the phrase writes ALL. */
    private static JsonObject unstringDelimiter(ValueStmt vs, boolean all) {
        JsonObject delimiter = new JsonObject();
        delimiter.add("operand", inspectOperand(vs));
        if (all) {
            delimiter.addProperty("all", true);
        }
        return delimiter;
    }

    /**
     * An INSPECT operand: a data reference with its qualifiers and subscripts,
     * or {"name": text} for a literal or figurative constant (red-dragon-sl30.40).
     */
    private static JsonObject inspectOperand(ValueStmt vs) {
        if (vs instanceof CallValueStmt && ((CallValueStmt) vs).getCall() != null) {
            return serializeRef(((CallValueStmt) vs).getCall());
        }
        CobolParser.LiteralContext repeated = allLiteralOf(vs);
        JsonObject lit = new JsonObject();
        lit.addProperty("name", repeated != null ? repeated.getText() : extractValueStmtText(vs));
        if (repeated == null) {
            markNumeric(lit, vs);
        }
        return lit;
    }

    /** The literal of an {@code ALL literal} figurative operand, else null. */
    private static CobolParser.LiteralContext allLiteralOf(ValueStmt vs) {
        if (!(vs instanceof LiteralValueStmt)) return null;
        Literal lit = ((LiteralValueStmt) vs).getLiteral();
        if (lit == null || !(lit.getCtx() instanceof CobolParser.LiteralContext)) return null;
        return allRepeatedLiteral((CobolParser.LiteralContext) lit.getCtx());
    }

    /** Adds "before"/"after" operands; a phrase may carry both. */
    private static void addBeforeAfter(
            JsonObject obj,
            List<io.proleap.cobol.asg.metamodel.procedure.inspect.BeforeAfterPhrase> phrases) {
        for (io.proleap.cobol.asg.metamodel.procedure.inspect.BeforeAfterPhrase bap : phrases) {
            String bound = (bap.getBeforeAfterType()
                    == io.proleap.cobol.asg.metamodel.procedure.inspect.BeforeAfterPhrase.BeforeAfterType.BEFORE)
                    ? "before" : "after";
            if (bap.getDataItemValueStmt() != null) {
                obj.add(bound, inspectOperand(bap.getDataItemValueStmt()));
            }
        }
    }

    /**
     * The element among {@code elements} that the parse-tree node {@code ctx} built,
     * so phrases are read in the order the parse tree holds them.
     */
    private static <T extends io.proleap.cobol.asg.metamodel.ASGElement> T builtFrom(
            org.antlr.v4.runtime.tree.ParseTree ctx, List<T> elements) {
        for (T element : elements) {
            if (element.getCtx() == ctx) {
                return element;
            }
        }
        return null;
    }

    private static JsonObject charactersPattern(
            io.proleap.cobol.asg.metamodel.procedure.inspect.Characters chars) {
        JsonObject forObj = new JsonObject();
        forObj.addProperty("mode", "CHARACTERS");
        addBeforeAfter(forObj, chars.getBeforeAfterPhrases());
        return forObj;
    }

    private static void addAllLeadingPatterns(JsonArray out, AllLeadingPhrase alp) {
        String mode = (alp.getAllLeadingsType() == AllLeadingPhrase.AllLeadingsType.ALL) ? "ALL" : "LEADING";
        for (AllLeading al : alp.getAllLeadings()) {
            JsonObject forObj = new JsonObject();
            forObj.addProperty("mode", mode);
            if (al.getPatternDataItemValueStmt() != null) {
                forObj.add("pattern", inspectOperand(al.getPatternDataItemValueStmt()));
            }
            addBeforeAfter(forObj, al.getBeforeAfterPhrases());
            out.add(forObj);
        }
    }

    /** A FOR's phrases in the order written: the parse tree's order of its children. */
    private static JsonArray tallyingPatterns(io.proleap.cobol.asg.metamodel.procedure.inspect.For forItem) {
        JsonArray out = new JsonArray();
        ParserRuleContext ctx = forItem.getCtx();
        for (int i = 0; i < ctx.getChildCount(); i++) {
            org.antlr.v4.runtime.tree.ParseTree child = ctx.getChild(i);
            if (child instanceof CobolParser.InspectCharactersContext) {
                out.add(charactersPattern(builtFrom(child, forItem.getCharacters())));
            } else if (child instanceof CobolParser.InspectAllLeadingsContext) {
                addAllLeadingPatterns(out, builtFrom(child, forItem.getAllLeadingPhrase()));
            }
        }
        return out;
    }

    private static JsonArray tallyingGroups(List<io.proleap.cobol.asg.metamodel.procedure.inspect.For> fors) {
        JsonArray groups = new JsonArray();
        for (io.proleap.cobol.asg.metamodel.procedure.inspect.For forItem : fors) {
            JsonObject groupObj = new JsonObject();
            if (forItem.getTallyCountDataItemCall() != null) {
                groupObj.add("target", serializeRef(forItem.getTallyCountDataItemCall()));
            }
            groupObj.add("patterns", tallyingPatterns(forItem));
            groups.add(groupObj);
        }
        return groups;
    }

    private static void addBy(JsonObject repObj, io.proleap.cobol.asg.metamodel.procedure.inspect.By by) {
        if (by != null && by.getByValueStmt() != null) {
            repObj.add("to", inspectOperand(by.getByValueStmt()));
        }
    }

    private static JsonObject replacingCharacters(
            io.proleap.cobol.asg.metamodel.procedure.inspect.ReplacingCharacters chars) {
        JsonObject repObj = new JsonObject();
        repObj.addProperty("mode", "CHARACTERS");
        addBy(repObj, chars.getBy());
        addBeforeAfter(repObj, chars.getBeforeAfterPhrases());
        return repObj;
    }

    private static void addReplacingAllLeadings(JsonArray out, ReplacingAllLeadings rals) {
        String mode;
        switch (rals.getReplacingAllLeadingsType()) {
            case FIRST: mode = "FIRST"; break;
            case LEADING: mode = "LEADING"; break;
            default: mode = "ALL"; break;
        }
        for (ReplacingAllLeading ral : rals.getAllLeadings()) {
            JsonObject repObj = new JsonObject();
            repObj.addProperty("mode", mode);
            if (ral.getPatternDataItemValueStmt() != null) {
                repObj.add("from", inspectOperand(ral.getPatternDataItemValueStmt()));
            }
            addBy(repObj, ral.getBy());
            addBeforeAfter(repObj, ral.getBeforeAfterPhrases());
            out.add(repObj);
        }
    }

    /** Every REPLACING phrase in the order written: each phrase's parse-tree children in turn. */
    private static JsonArray replacings(List<io.proleap.cobol.asg.metamodel.procedure.inspect.Replacing> replacings) {
        JsonArray out = new JsonArray();
        for (io.proleap.cobol.asg.metamodel.procedure.inspect.Replacing replacing : replacings) {
            ParserRuleContext ctx = replacing.getCtx();
            for (int i = 0; i < ctx.getChildCount(); i++) {
                org.antlr.v4.runtime.tree.ParseTree child = ctx.getChild(i);
                if (child instanceof CobolParser.InspectReplacingCharactersContext) {
                    out.add(replacingCharacters(builtFrom(child, replacing.getCharacters())));
                } else if (child instanceof CobolParser.InspectReplacingAllLeadingsContext) {
                    addReplacingAllLeadings(out, builtFrom(child, replacing.getAllLeadings()));
                }
            }
        }
        return out;
    }

    private static JsonObject serializeInspect(InspectStatement stmt) {
        JsonObject obj = newStatement("INSPECT");
        try {
            if (stmt.getDataItemCall() != null) {
                obj.add("source", serializeMoveOperand(stmt.getDataItemCall()));
            }
            InspectStatement.InspectType inspType = stmt.getInspectType();
            if (inspType == InspectStatement.InspectType.TALLYING && stmt.getTallying() != null) {
                obj.addProperty("inspect_type", "TALLYING");
                obj.add("tallying_groups", tallyingGroups(stmt.getTallying().getFors()));
            } else if (inspType == InspectStatement.InspectType.REPLACING && stmt.getReplacing() != null) {
                obj.addProperty("inspect_type", "REPLACING");
                obj.add("replacings", replacings(List.of(stmt.getReplacing())));
            } else if (inspType == InspectStatement.InspectType.TALLYING_REPLACING
                    && stmt.getTallyingReplacing() != null) {
                obj.addProperty("inspect_type", "TALLYING_REPLACING");
                obj.add("tallying_groups", tallyingGroups(stmt.getTallyingReplacing().getFors()));
                obj.add("replacings", replacings(stmt.getTallyingReplacing().getReplacings()));
            } else if (inspType == InspectStatement.InspectType.CONVERTING && stmt.getConverting() != null) {
                obj.addProperty("inspect_type", "CONVERTING");
                io.proleap.cobol.asg.metamodel.procedure.inspect.Converting conv = stmt.getConverting();
                if (conv.getFromValueStmt() != null) {
                    obj.add("converting_from", inspectOperand(conv.getFromValueStmt()));
                }
                if (conv.getTo() != null && conv.getTo().getToValueStmt() != null) {
                    obj.add("converting_to", inspectOperand(conv.getTo().getToValueStmt()));
                }
                addBeforeAfter(obj, conv.getBeforeAfterPhrases());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract INSPECT operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeSearch(SearchStatement stmt) {
        JsonObject obj = newStatement("SEARCH");
        try {
            // Table being searched
            if (stmt.getDataCall() != null) {
                obj.add("table", serializeRef(stmt.getDataCall()));
            }

            // SEARCH ALL: the whole table is searched, whatever its index holds.
            if (((CobolParser.SearchStatementContext) stmt.getCtx()).ALL() != null) {
                obj.addProperty("all", true);
            }

            // VARYING index variable (optional)
            if (stmt.getVaryingPhrase() != null && stmt.getVaryingPhrase().getDataCall() != null) {
                obj.add("varying", serializeRef(stmt.getVaryingPhrase().getDataCall()));
            }

            // WHEN clauses
            JsonArray whens = new JsonArray();
            for (io.proleap.cobol.asg.metamodel.procedure.search.WhenPhrase when : stmt.getWhenPhrases()) {
                JsonObject whenObj = new JsonObject();
                // Structured condition — same serializer the IF path uses.
                if (when.getCondition() != null) {
                    whenObj.add("condition", serializeConditionNode(when.getCondition()));
                }
                // Serialize child statements
                if (when.getWhenType()
                        == io.proleap.cobol.asg.metamodel.procedure.search.WhenPhrase.WhenType.NEXT_SENTENCE) {
                    JsonArray children = new JsonArray();
                    children.add(nextSentence(when.getCtx()));
                    whenObj.add("children", children);
                } else if (when.getStatements() != null && !when.getStatements().isEmpty()) {
                    JsonArray children = serializeStatements(when.getStatements());
                    if (children.size() > 0) {
                        whenObj.add("children", children);
                    }
                }
                whens.add(whenObj);
            }
            obj.add("whens", whens);

            // AT END clause
            if (stmt.getAtEndPhrase() != null && stmt.getAtEndPhrase().getStatements() != null) {
                JsonArray atEndChildren = serializeStatements(stmt.getAtEndPhrase().getStatements());
                if (atEndChildren.size() > 0) {
                    obj.add("at_end", atEndChildren);
                }
            }
        } catch (Exception e) {
            LOG.fine("Could not extract SEARCH operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeCall(CallStatement stmt) {
        JsonObject obj = newStatement("CALL");
        try {
            // Callee. Cobol.g4:1241 is `CALL (identifier | literal)`, and the two
            // arms mean different things at run time: a literal names the program
            // outright, while an identifier's *contents* name it. ProLeap models
            // the identifier arm as a CallValueStmt, so it gets the same structured
            // reference every other operand does (name + subscripts + ref-mod +
            // qualifiers) — `CALL WS-PROG(1:8)` is a common idiom and flattening it
            // to text would call the wrong program. (red-dragon-jgra)
            ValueStmt programValueStmt = stmt.getProgramValueStmt();
            if (programValueStmt != null) {
                Call programCall =
                        (programValueStmt instanceof CallValueStmt)
                                ? ((CallValueStmt) programValueStmt).getCall()
                                : null;
                if (programCall != null) {
                    obj.add("program_ref", serializeRef(programCall));
                } else {
                    String progName = extractValueStmtText(programValueStmt);
                    // Strip quotes from literal program names (e.g., 'SUBPROG' -> SUBPROG)
                    progName = progName.replaceAll("^['\"]|['\"]$", "");
                    obj.addProperty("program", progName);
                }
            }
            // USING parameters — each BY REFERENCE/VALUE/CONTENT clause may carry
            // multiple operands (e.g. CALL 'X' USING BY REFERENCE WS-A WS-B).
            // Emit one JSON param object per operand, not one per clause.
            if (stmt.getUsingPhrase() != null && stmt.getUsingPhrase().getUsingParameters() != null) {
                JsonArray params = new JsonArray();
                for (UsingParameter param : stmt.getUsingPhrase().getUsingParameters()) {
                    if (param.getByReferencePhrase() != null
                            && param.getByReferencePhrase().getByReferences() != null) {
                        for (ByReference br : param.getByReferencePhrase().getByReferences()) {
                            JsonObject paramObj = new JsonObject();
                            paramObj.addProperty("type", "REFERENCE");
                            if (br.getByReferenceType() == ByReference.ByReferenceType.OMITTED) {
                                paramObj.addProperty("omitted", true);
                            } else if (br.getByReferenceType() == ByReference.ByReferenceType.ADDRESS_OF) {
                                addUsingOperand(paramObj, addressOfOperand(br.getValueStmt()));
                                paramObj.addProperty("address_of", true);
                            } else {
                                addUsingOperand(paramObj, usingOperand(br.getValueStmt()));
                                if (br.getByReferenceType() == ByReference.ByReferenceType.STRING
                                        || br.getByReferenceType() == ByReference.ByReferenceType.INTEGER) {
                                    paramObj.addProperty("is_literal", true);
                                }
                            }
                            params.add(paramObj);
                        }
                    } else if (param.getByContentPhrase() != null
                            && param.getByContentPhrase().getByContents() != null) {
                        for (ByContent bc : param.getByContentPhrase().getByContents()) {
                            JsonObject paramObj = new JsonObject();
                            paramObj.addProperty("type", "CONTENT");
                            if (bc.getByContentType() == ByContent.ByContentType.ADDRESS_OF) {
                                addUsingOperand(paramObj, addressOfOperand(bc.getValueStmt()));
                                paramObj.addProperty("address_of", true);
                            } else {
                                addUsingOperand(paramObj, usingOperand(bc.getValueStmt()));
                            }
                            if (bc.getValueStmt() instanceof io.proleap.cobol.asg.metamodel.valuestmt.LiteralValueStmt) {
                                paramObj.addProperty("is_literal", true);
                            }
                            params.add(paramObj);
                        }
                    } else if (param.getByValuePhrase() != null
                            && param.getByValuePhrase().getByValues() != null) {
                        for (ByValue bv : param.getByValuePhrase().getByValues()) {
                            JsonObject paramObj = new JsonObject();
                            paramObj.addProperty("type", "VALUE");
                            if (bv.getByValueType() == ByValue.ByValueType.ADDRESS_OF) {
                                addUsingOperand(paramObj, addressOfOperand(bv.getValueStmt()));
                                paramObj.addProperty("address_of", true);
                            } else {
                                addUsingOperand(paramObj, usingOperand(bv.getValueStmt()));
                            }
                            if (bv.getValueStmt() instanceof io.proleap.cobol.asg.metamodel.valuestmt.LiteralValueStmt) {
                                paramObj.addProperty("is_literal", true);
                            }
                            params.add(paramObj);
                        }
                    }
                }
                obj.add("using", params);
            }
            // GIVING
            if (stmt.getGivingPhrase() != null && stmt.getGivingPhrase().getGivingCall() != null) {
                obj.add("giving", serializeRef(stmt.getGivingPhrase().getGivingCall()));
            }
        } catch (Exception e) {
            LOG.fine("Could not extract CALL operands: " + e.getMessage());
        }
        addPhrase(obj, "on_exception", stmt.getOnExceptionClause());
        addPhrase(obj, "on_exception", stmt.getOnOverflowPhrase());
        addPhrase(obj, "not_on_exception", stmt.getNotOnExceptionClause());
        return obj;
    }

    private static JsonObject serializeAlter(AlterStatement stmt) {
        JsonObject obj = newStatement("ALTER");
        try {
            if (stmt.getProceedTos() != null) {
                JsonArray proceeds = new JsonArray();
                for (ProceedTo pt : stmt.getProceedTos()) {
                    JsonObject ptObj = new JsonObject();
                    if (pt.getSourceCall() != null) {
                        ptObj.addProperty("source", extractCallName(pt.getSourceCall()));
                    }
                    if (pt.getTargetCall() != null) {
                        ptObj.addProperty("target", extractCallName(pt.getTargetCall()));
                    }
                    proceeds.add(ptObj);
                }
                obj.add("proceed_tos", proceeds);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract ALTER operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeEntry(EntryStatement stmt) {
        JsonObject obj = newStatement("ENTRY");
        try {
            if (stmt.getEntryValueStmt() != null) {
                String entryName = extractValueStmtText(stmt.getEntryValueStmt());
                entryName = entryName.replaceAll("^['\"]|['\"]$", "");
                obj.addProperty("entry_name", entryName);
            }
            if (stmt.getUsingCalls() != null && !stmt.getUsingCalls().isEmpty()) {
                JsonArray usingArr = new JsonArray();
                for (Call call : stmt.getUsingCalls()) {
                    usingArr.add(extractCallName(call));
                }
                obj.add("using", usingArr);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract ENTRY operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeCancel(CancelStatement stmt) {
        JsonObject obj = newStatement("CANCEL");
        try {
            if (stmt.getCancelCalls() != null) {
                JsonArray programs = new JsonArray();
                for (io.proleap.cobol.asg.metamodel.procedure.cancel.CancelCall cc : stmt.getCancelCalls()) {
                    if (cc.getValueStmt() != null) {
                        String name = extractValueStmtText(cc.getValueStmt());
                        name = name.replaceAll("^['\"]|['\"]$", "");
                        programs.add(name);
                    }
                }
                obj.add("programs", programs);
            }
        } catch (Exception e) {
            LOG.fine("Could not extract CANCEL operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeAccept(AcceptStatement stmt) {
        JsonObject obj = newStatement("ACCEPT");
        try {
            if (stmt.getAcceptCall() != null) {
                obj.add("target", serializeRef(stmt.getAcceptCall()));
            }
            // FROM device — AcceptStatement.AcceptType distinguishes
            // DATE/DAY/TIME vs. environment name vs. mnemonic.
            // For simplicity, default to CONSOLE (user input).
            if (stmt.getAcceptType() != null) {
                obj.addProperty("from_device", stmt.getAcceptType().name());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract ACCEPT operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeOpen(OpenStatement stmt) {
        JsonObject obj = newStatement("OPEN");
        try {
            JsonArray modeGroups = new JsonArray();

            // INPUT files
            List<io.proleap.cobol.asg.metamodel.procedure.open.InputPhrase> inputPhrases = stmt.getInputPhrases();
            if (inputPhrases != null && !inputPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                inputPhrases.stream()
                    .flatMap(ip -> ip.getInputs().stream())
                    .map(io.proleap.cobol.asg.metamodel.procedure.open.Input::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "INPUT");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            // OUTPUT files
            List<io.proleap.cobol.asg.metamodel.procedure.open.OutputPhrase> outputPhrases = stmt.getOutputPhrases();
            if (outputPhrases != null && !outputPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                outputPhrases.stream()
                    .flatMap(op -> op.getOutputs().stream())
                    .map(io.proleap.cobol.asg.metamodel.procedure.open.Output::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "OUTPUT");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            // I-O files
            List<io.proleap.cobol.asg.metamodel.procedure.open.InputOutputPhrase> ioPhrases = stmt.getInputOutputPhrases();
            if (ioPhrases != null && !ioPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                ioPhrases.stream()
                    .flatMap(iop -> iop.getFileCalls().stream())
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "I-O");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            // EXTEND files
            List<io.proleap.cobol.asg.metamodel.procedure.open.ExtendPhrase> extendPhrases = stmt.getExtendPhrases();
            if (extendPhrases != null && !extendPhrases.isEmpty()) {
                JsonArray files = new JsonArray();
                extendPhrases.stream()
                    .flatMap(ep -> ep.getFileCalls().stream())
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
                if (files.size() > 0) {
                    JsonObject grp = new JsonObject();
                    grp.addProperty("mode", "EXTEND");
                    grp.add("files", files);
                    modeGroups.add(grp);
                }
            }

            obj.add("mode_groups", modeGroups);
        } catch (Exception e) {
            LOG.fine("Could not extract OPEN operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeClose(CloseStatement stmt) {
        JsonObject obj = newStatement("CLOSE");
        try {
            JsonArray files = new JsonArray();
            if (stmt.getCloseFiles() != null) {
                stmt.getCloseFiles().stream()
                    .map(io.proleap.cobol.asg.metamodel.procedure.close.CloseFile::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(files::add);
            }
            obj.add("files", files);
            JsonArray withLock = new JsonArray();
            if (stmt.getCloseFiles() != null) {
                stmt.getCloseFiles().stream()
                    .filter(StatementSerializer::isClosedWithLock)
                    .map(io.proleap.cobol.asg.metamodel.procedure.close.CloseFile::getFileCall)
                    .filter(c -> c != null)
                    .map(StatementSerializer::extractCallName)
                    .forEach(withLock::add);
            }
            obj.add("with_lock", withLock);
        } catch (Exception e) {
            LOG.fine("Could not extract CLOSE operands: " + e.getMessage());
        }
        return obj;
    }

    private static boolean isClosedWithLock(
            io.proleap.cobol.asg.metamodel.procedure.close.CloseFile closeFile) {
        io.proleap.cobol.asg.metamodel.procedure.close.CloseRelativeStatement relative =
            closeFile.getCloseRelativeStatement();
        return relative != null
            && relative.getWithType()
                == io.proleap.cobol.asg.metamodel.procedure.close.CloseRelativeStatement.WithType.LOCK;
    }

    private static JsonObject serializeRead(ReadStatement stmt) {
        JsonObject obj = newStatement("READ");
        try {
            if (stmt.getFileCall() != null) {
                obj.addProperty("file_name", extractCallName(stmt.getFileCall()));
            }
            if (((CobolParser.ReadStatementContext) stmt.getCtx()).NEXT() != null) {
                obj.addProperty("next_record", true);
            }
            io.proleap.cobol.asg.metamodel.procedure.read.Into into = stmt.getInto();
            if (into != null && into.getIntoCall() != null) {
                obj.add("into", serializeRef(into.getIntoCall()));
            }

            // KEY IS clause
            io.proleap.cobol.asg.metamodel.procedure.read.Key key = stmt.getKey();
            if (key != null && key.getKeyCall() != null) {
                obj.add("key", serializeRef(key.getKeyCall()));
            } else {
                obj.addProperty("key", "");
            }

            // AT END / NOT AT END
            io.proleap.cobol.asg.metamodel.procedure.AtEndPhrase atEnd = stmt.getAtEnd();
            if (atEnd != null && atEnd.getStatements() != null) {
                obj.add("at_end", serializeStatements(atEnd.getStatements()));
            } else {
                obj.add("at_end", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotAtEndPhrase notAtEnd = stmt.getNotAtEndPhrase();
            if (notAtEnd != null && notAtEnd.getStatements() != null) {
                obj.add("not_at_end", serializeStatements(notAtEnd.getStatements()));
            } else {
                obj.add("not_at_end", new JsonArray());
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract READ operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeWrite(WriteStatement stmt) {
        JsonObject obj = newStatement("WRITE");
        try {
            if (stmt.getRecordCall() != null) {
                obj.addProperty("record_name", extractCallName(stmt.getRecordCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.write.From from = stmt.getFrom();
            if (from != null && from.getFromValueStmt() != null) {
                obj.add("from_field", writeFromOperand(from.getFromValueStmt()));
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract WRITE operands: " + e.getMessage());
        }
        return obj;
    }

    /** A WRITE FROM sender: a data reference with its qualifiers, or a literal's text. */
    private static JsonObject writeFromOperand(ValueStmt vs) {
        if (vs instanceof CallValueStmt && ((CallValueStmt) vs).getCall() != null) {
            return serializeRef(((CallValueStmt) vs).getCall());
        }
        JsonObject literal = new JsonObject();
        literal.addProperty("name", extractValueStmtText(vs));
        markNumeric(literal, vs);
        return literal;
    }

    private static JsonObject serializeRewrite(RewriteStatement stmt) {
        JsonObject obj = newStatement("REWRITE");
        try {
            if (stmt.getRecordCall() != null) {
                obj.addProperty("record_name", extractCallName(stmt.getRecordCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.rewrite.From from = stmt.getFrom();
            if (from != null && from.getFromCall() != null) {
                obj.add("from_field", serializeRef(from.getFromCall()));
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract REWRITE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeStart(StartStatement stmt) {
        JsonObject obj = newStatement("START");
        try {
            if (stmt.getFileCall() != null) {
                obj.addProperty("file_name", extractCallName(stmt.getFileCall()));
            }
            io.proleap.cobol.asg.metamodel.procedure.start.Key key = stmt.getKey();
            if (key != null && key.getComparisonCall() != null) {
                obj.add("key", serializeRef(key.getComparisonCall()));
                // Relational operator from KeyType enum
                if (key.getKeyType() != null) {
                    String relop;
                    switch (key.getKeyType()) {
                        case GREATER: relop = ">"; break;
                        case GREATER_OR_EQUAL: relop = ">="; break;
                        case EQUAL: default: relop = "="; break;
                    }
                    obj.addProperty("relop", relop);
                } else {
                    obj.addProperty("relop", "=");
                }
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract START operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeDelete(DeleteStatement stmt) {
        JsonObject obj = newStatement("DELETE");
        try {
            if (stmt.getFileCall() != null) {
                obj.addProperty("file_name", extractCallName(stmt.getFileCall()));
            }

            // INVALID KEY / NOT INVALID KEY
            io.proleap.cobol.asg.metamodel.procedure.InvalidKeyPhrase invalidKey = stmt.getInvalidKeyPhrase();
            if (invalidKey != null && invalidKey.getStatements() != null) {
                obj.add("invalid_key", serializeStatements(invalidKey.getStatements()));
            } else {
                obj.add("invalid_key", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotInvalidKeyPhrase notInvalidKey = stmt.getNotInvalidKeyPhrase();
            if (notInvalidKey != null && notInvalidKey.getStatements() != null) {
                obj.add("not_invalid_key", serializeStatements(notInvalidKey.getStatements()));
            } else {
                obj.add("not_invalid_key", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract DELETE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeXmlGenerate(XmlGenerateStatement stmt) {
        JsonObject obj = newStatement("XML_GENERATE");
        try {
            if (stmt.getReceiverCall() != null) {
                obj.addProperty("xml_document", extractCallName(stmt.getReceiverCall()));
            }
            if (stmt.getFromCall() != null) {
                obj.addProperty("from_record", extractCallName(stmt.getFromCall()));
            }
            if (stmt.getCountCall() != null) {
                obj.addProperty("count_in", extractCallName(stmt.getCountCall()));
            }

            // ON EXCEPTION / NOT ON EXCEPTION
            io.proleap.cobol.asg.metamodel.procedure.OnExceptionClause onException = stmt.getOnExceptionClause();
            if (onException != null && onException.getStatements() != null) {
                obj.add("on_exception", serializeStatements(onException.getStatements()));
            } else {
                obj.add("on_exception", new JsonArray());
            }
            io.proleap.cobol.asg.metamodel.procedure.NotOnExceptionClause notOnException = stmt
                    .getNotOnExceptionClause();
            if (notOnException != null && notOnException.getStatements() != null) {
                obj.add("not_on_exception", serializeStatements(notOnException.getStatements()));
            } else {
                obj.add("not_on_exception", new JsonArray());
            }
        } catch (Exception e) {
            LOG.fine("Could not extract XML GENERATE operands: " + e.getMessage());
        }
        return obj;
    }

    private static JsonObject serializeExecCics(ExecCicsStatement stmt) {
        JsonObject obj = newStatement("EXEC_CICS");
        String text = stmt.getExecCicsText();
        if (text != null) {
            obj.addProperty("exec_cics_text", text);
        }
        return obj;
    }

    private static JsonObject serializeExecSql(ExecSqlStatement stmt) {
        // Opaque passthrough, exactly like serializeExecCics: emit getExecSqlText()
        // verbatim (the full "EXEC SQL ... END-EXEC" form). The bridge does no SQL
        // parsing; envelope removal + parsing happen in the Python/squall layer.
        JsonObject obj = newStatement("EXEC_SQL");
        String text = stmt.getExecSqlText();
        if (text != null) {
            obj.addProperty("exec_sql_text", text);
        }
        return obj;
    }

    private static JsonObject serializeUnknown(StatementType stmtType) {
        LOG.warning("Unknown statement type: " + stmtType);
        return newStatement(stmtType.toString());
    }

    private static JsonObject newStatement(String type) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", type);
        return obj;
    }

    /**
     * Extracts a human-readable name from a ProLeap Call object.
     */
    static String extractCallName(Call call) {
        if (call == null) {
            return "";
        }
        // Unwrap delegate calls to reach the actual underlying call
        Call unwrapped = call.unwrap();

        // A TABLE_CALL is a subscripted reference; emit the BARE base name. The
        // subscripts travel separately (see extractSubscripts / serializeRef);
        // they are no longer flattened into the name string. (red-dragon-6ddr)
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof TableCall tableCall) {
            String baseName = tableCall.getName();
            return (baseName != null) ? baseName : unwrapped.toString();
        }

        String name = call.getName();
        if (name != null) {
            return name;
        }
        // ProLeap does not model COBOL special registers (RETURN-CODE, SORT-RETURN,
        // TALLY, ...) as data items, so the Call's getName() is null. Recover the
        // verbatim source identifier from the parse-tree context (e.g. the literal
        // text "RETURN-CODE") so the frontend can route it; without this the name
        // degrades to the opaque call.toString() ("name=[null]"). (red-dragon-o8uq)
        String ctxText = callContextText(unwrapped);
        return (ctxText != null) ? ctxText : call.toString();
    }

    /** First parse-tree token text of a Call's grammar context, or null. */
    private static String callContextText(Call call) {
        if (!(call instanceof ASGElementImpl)) {
            return null;
        }
        ParserRuleContext ctx = ((ASGElementImpl) call).getCtx();
        if (ctx == null || ctx.getStart() == null) {
            return null;
        }
        return ctx.getStart().getText();
    }

    /**
     * All subscripts of a (possibly delegated) TABLE_CALL, in source order, each
     * as a STRUCTURED expression node ({@code {kind:"ref"/"lit"/"binop"/...}}) —
     * the same shape the COMPUTE/IF value-stmt serializer emits and that the
     * Python {@code expr_from_dict} consumes. Reuses {@link #serializeFromValue}
     * so an arithmetic or nested subscript (e.g. {@code TBL(WS-I + 1)}) is carried
     * as a real expression tree, not a string (red-dragon-l445). Empty array for
     * any non-table call.
     */
    private static JsonArray extractSubscripts(Call call) {
        if (call == null) {
            return new JsonArray();
        }
        Call unwrapped = call.unwrap();
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof TableCall tableCall) {
            JsonArray subscripts = serializeSubscripts(tableCall.getSubscripts());
            if (subscripts.size() > 0) {
                return subscripts;
            }
        }
        if (!(unwrapped instanceof ASGElementImpl)) {
            return new JsonArray();
        }
        JsonArray fromQualifier = new JsonArray();
        collectInTableSubscripts(((ASGElementImpl) unwrapped).getCtx(), fromQualifier);
        return fromQualifier;
    }

    private static JsonArray serializeSubscripts(List<Subscript> subscripts) {
        JsonArray arr = new JsonArray();
        if (subscripts != null) {
            for (Subscript sub : subscripts) {
                arr.add(isAllSubscript(sub.getCtx())
                        ? allSubscriptNode()
                        : serializeFromValue(sub.getSubscriptValueStmt()));
            }
        }
        return arr;
    }

    /**
     * Subscripts of a level-88 reference such as {@code FLAG-ON(2)}. A condition
     * name is not a TABLE_CALL, so its subscripts hang off the reference's
     * {@link ConditionNameSubscriptReference} list rather than off the condition
     * call (red-dragon-8u47).
     */
    private static JsonArray extractConditionSubscripts(ConditionNameReference ref) {
        JsonArray arr = new JsonArray();
        if (ref == null || ref.getConditionNameSubscriptReferences() == null) {
            return arr;
        }
        for (ConditionNameSubscriptReference subRef : ref.getConditionNameSubscriptReferences()) {
            arr.addAll(serializeSubscripts(subRef.getSubscripts()));
        }
        return arr;
    }

    /**
     * Structured reference operand: {@code {name: <bare base>, subscripts:[...],
     * ref_mod_start?, ref_mod_length?, qualifiers?}}. Subscripts and ref-mod keys
     * are present only when non-empty. The single serializer for any subscriptable
     * data reference. (red-dragon-6ddr)
     */
    static JsonObject serializeRef(Call call) {
        JsonObject obj = new JsonObject();
        obj.addProperty("name", extractCallName(call));
        JsonArray subs = extractSubscripts(call);
        if (subs.size() > 0) {
            obj.add("subscripts", subs);
        }
        CobolParser.ReferenceModifierContext refMod = getRefMod(call);
        if (refMod != null) {
            JsonObject rm = serializeRefMod(refMod);
            obj.add("ref_mod_start", rm.get("ref_mod_start"));
            if (rm.has("ref_mod_length")) {
                obj.add("ref_mod_length", rm.get("ref_mod_length"));
            }
        }
        JsonArray qualifiers = extractQualifiers(call);
        if (qualifiers.size() > 0) {
            obj.add("qualifiers", qualifiers);
        }
        return obj;
    }

    /**
     * Navigates a Call's grammar context to find its referenceModifier, or null if absent.
     * ProLeap models ref-mod fields as TABLE_CALL; the grammar context has tableCall().referenceModifier().
     */
    private static CobolParser.ReferenceModifierContext getRefMod(Call call) {
        if (call == null) return null;
        Call unwrapped = call.unwrap();
        if (!(unwrapped instanceof ASGElementImpl)) return null;
        ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
        if (ctx == null) return null;

        // If ctx is already a TableCallContext, call referenceModifier() directly
        if (ctx instanceof CobolParser.TableCallContext) {
            CobolParser.ReferenceModifierContext direct =
                    ((CobolParser.TableCallContext) ctx).referenceModifier();
            if (direct != null) return direct;
        }

        // Otherwise, try to find tableCall() method (e.g. for IdentifierContext)
        try {
            java.lang.reflect.Method m = ctx.getClass().getMethod("tableCall");
            CobolParser.TableCallContext tc = (CobolParser.TableCallContext) m.invoke(ctx);
            if (tc != null) {
                CobolParser.ReferenceModifierContext rm = tc.referenceModifier();
                if (rm != null) return rm;
            }
        } catch (Exception e) {
            // ctx may not have a tableCall() method (e.g. if it's not an identifierContext);
            // reflection lets us probe without a compile-time cast — fall through.
        }

        // A QUALIFIED data reference (X OF Y(2:8)) wraps the tableCall +
        // referenceModifier deeper in the parse tree (qualifiedDataName), so the
        // direct/tableCall() lookups above miss it. Search the subtree for the
        // first ReferenceModifierContext. (CardDemo COTRN02C: TRNAMTI OF COTRN2AI.)
        return firstReferenceModifierDescendant(ctx);
    }

    /**
     * Depth-first pre-order walk of the subtree an operand IS, stopping at the
     * first node {@code accepts} matches.
     *
     * <p>The containment rules of an operand's subtree live here and nowhere
     * else. Three of them:
     *
     * <ul>
     *   <li>The walk starts AT the operand, so a referenceModifier <em>enclosing</em>
     *       it is outside the walk entirely — a slice bound serialized in its own
     *       right correctly sees itself as the operand.</li>
     *   <li>The walk never descends below a {@link
     *       CobolParser.ReferenceModifierContext} it meets inside the operand:
     *       a name, function call or special register written in a slice's bounds
     *       belongs to the BOUND, never to the sliced field. Returning one in the
     *       operand's place dropped the sliced field and both bounds, so
     *       {@code MOVE M(1:FUNCTION LENGTH(M)) TO D} moved a number where text
     *       belonged; attributing one as the operand's qualifier resolved
     *       {@code FA OF GA(1:FB OF GB)} against GB. Six defects
     *       (red-dragon-jscx, -nwm5, -pe45, -35do, -twfl, -64s4) were one
     *       traversal at a time forgetting this; a probe built on this walker
     *       cannot forget it, because it does not state it.</li>
     *   <li>Likewise it never descends below a {@link CobolParser.SubscriptContext}:
     *       {@code AX-2 IN AX (CX-SUB OF CX)} is qualified by AX alone, CX qualifies
     *       the subscript's own operand (red-dragon-sl30.34).</li>
     * </ul>
     *
     * @return the first accepted node, or {@code null} when none was accepted —
     *     a predicate that records what it sees and never accepts therefore
     *     walks the whole subtree, which is how the collecting probes use it.
     */
    private static org.antlr.v4.runtime.tree.ParseTree walkOperand(
            org.antlr.v4.runtime.tree.ParseTree operand,
            java.util.function.Predicate<org.antlr.v4.runtime.tree.ParseTree> accepts) {
        return walkOperand(operand, operand, accepts);
    }

    private static org.antlr.v4.runtime.tree.ParseTree walkOperand(
            org.antlr.v4.runtime.tree.ParseTree node,
            org.antlr.v4.runtime.tree.ParseTree operand,
            java.util.function.Predicate<org.antlr.v4.runtime.tree.ParseTree> accepts) {
        if (node == null) {
            return null;
        }
        if (accepts.test(node)) {
            return node;
        }
        if (node != operand
                && (node instanceof CobolParser.ReferenceModifierContext
                        || node instanceof CobolParser.SubscriptContext)) {
            return null;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            org.antlr.v4.runtime.tree.ParseTree found =
                    walkOperand(node.getChild(i), operand, accepts);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    /**
     * The first ReferenceModifierContext inside {@code ctx} — the operand's OWN
     * modifier, since a pre-order walk reaches it before any nested in its bounds
     * ({@code M(1:N(1:2))}).
     */
    private static CobolParser.ReferenceModifierContext firstReferenceModifierDescendant(
            ParserRuleContext ctx) {
        return (CobolParser.ReferenceModifierContext)
                walkOperand(ctx, n -> n != ctx && n instanceof CobolParser.ReferenceModifierContext);
    }

    /**
     * Extracts the base data name for a call, stripping subscript/refmod notation.
     * For TABLE_CALL: uses the first token of the grammar context (the data name token).
     * Falls back to extractCallName for non-TABLE_CALL types.
     */
    private static String extractCallBaseName(Call call) {
        if (call == null) return "";
        Call unwrapped = call.unwrap();
        if (unwrapped.getCallType() == Call.CallType.TABLE_CALL && unwrapped instanceof ASGElementImpl) {
            ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
            if (ctx != null) {
                org.antlr.v4.runtime.Token start = ctx.getStart();
                if (start != null) return start.getText();
            }
        }
        String name = call.getName();
        return (name != null) ? name : call.toString();
    }

    /**
     * Serializes a PERFORM VARYING FROM value as a structured expression node so
     * the Python frontend can evaluate it (rather than treating the flattened text
     * as an opaque literal). Recognises {@code LENGTH OF <field>} structurally from
     * the parse-tree special-register context, emitting
     * {@code {"kind":"length_of","name":"<field>"}}. Otherwise serializes the
     * underlying arithmetic expression (refs, literals, ref-mod, binops); failing
     * that, falls back to a {@code {"kind":"lit","value":<text>}} node.
     */
    /**
     * If a MOVE sending-area ValueStmt is a {@code LENGTH OF <field>} special
     * register, returns a structured {@code {"kind":"length_of","name":"<field>"}}
     * node (the leaf data-name); otherwise returns {@code null}. Structural — no
     * text parsing. Mirrors {@link #serializeFromValue}'s length_of handling.
     */
    private static JsonObject serializeMoveLengthOfSource(ValueStmt vs) {
        if (vs == null) {
            return null;
        }
        ParserRuleContext ctx;
        try {
            ctx = vs.getCtx();
        } catch (Exception e) {
            return null;
        }
        if (ctx == null) {
            return null;
        }
        // A `LENGTH OF G` appearing INSIDE a reference modifier (e.g.
        // MOVE SRC(1:LENGTH OF G) TO ...) is the slice length, not the sending
        // operand — leave it for the ref-mod path. (red-dragon)
        CobolParser.SpecialRegisterContext sr = lengthOfSpecialRegisterOperand(ctx);
        if (sr == null) {
            return null;
        }
        return lengthOfNode(sr.identifier());
    }

    /**
     * The {@code length_of} node for the identifier a LENGTH OF measures: its leaf
     * data-name and the OF/IN qualifiers written on it.
     */
    private static JsonObject lengthOfNode(CobolParser.IdentifierContext id) {
        JsonObject obj = new JsonObject();
        obj.addProperty("kind", "length_of");
        obj.addProperty("name", id != null ? leafDataName(id) : "");
        JsonArray qualifiers = new JsonArray();
        if (id != null) {
            collectInDataQualifiers(id, qualifiers);
        }
        if (qualifiers.size() > 0) {
            obj.add("qualifiers", qualifiers);
        }
        return obj;
    }

    private static JsonElement serializeFromValue(ValueStmt vs) {
        if (vs == null) {
            return litNode("");
        }
        ParserRuleContext ctx = null;
        try {
            ctx = vs.getCtx();
        } catch (Exception e) {
            // fall through
        }
        if (ctx != null) {
            CobolParser.SpecialRegisterContext sr = lengthOfSpecialRegisterOperand(ctx);
            if (sr != null) {
                return lengthOfNode(sr.identifier());
            }
        }
        if (vs instanceof ArithmeticValueStmt) {
            return serializeArithmeticExpr((ArithmeticValueStmt) vs);
        }
        // An identifier keeps its subscripts, slice and qualifiers structured:
        // flat text glued them into unresolvable names such as "EL(S1)",
        // "NUMF(1:LENGTHOFN)" or "FBOFGB" (red-dragon-sl30.9, -twfl, -2afo).
        CobolParser.IdentifierContext id = wholeOperandIdentifier(ctx);
        if (id != null) {
            return serializeIdentifierCtx(id);
        }
        if (ctx instanceof CobolParser.LiteralContext) {
            return serializeLiteralCtx((CobolParser.LiteralContext) ctx);
        }
        if (ctx instanceof CobolParser.IntegerLiteralContext) {
            return litNode(ctx.getText());
        }
        String text = (ctx != null) ? ctx.getText() : extractValueStmtText(vs);
        JsonObject ref = new JsonObject();
        ref.addProperty("kind", "ref");
        ref.addProperty("name", text);
        return ref;
    }

    /**
     * The identifier an operand IS — one that spans {@code ctx} end to end — or
     * {@code null} when {@code ctx} is anything larger.
     *
     * <p>The span test is the same containment discipline {@link #walkOperand}
     * enforces: an identifier nested inside a wider expression is one operand of
     * it, never a replacement for it.
     */
    private static CobolParser.IdentifierContext wholeOperandIdentifier(ParserRuleContext ctx) {
        if (ctx == null) {
            return null;
        }
        if (ctx instanceof CobolParser.IdentifierContext) {
            return (CobolParser.IdentifierContext) ctx;
        }
        for (int i = 0; i < ctx.getChildCount(); i++) {
            org.antlr.v4.runtime.tree.ParseTree child = ctx.getChild(i);
            if (!(child instanceof ParserRuleContext)) {
                continue;
            }
            ParserRuleContext rule = (ParserRuleContext) child;
            if (rule.getStart() == ctx.getStart() && rule.getStop() == ctx.getStop()) {
                return wholeOperandIdentifier(rule);
            }
        }
        return null;
    }

    /**
     * The {@code LENGTH OF} specialRegister an operand IS, or {@code null} when
     * the operand merely contains one.
     *
     * <p>A register reached through {@code operand}'s own referenceModifier
     * computes a slice bound — {@code NUMF(1:LENGTH OF N)} is four bytes of NUMF,
     * not the number 4. Returning it discarded the sliced field and both bounds
     * (red-dragon-twfl); {@link #walkOperand} never reaches it.
     */
    private static CobolParser.SpecialRegisterContext lengthOfSpecialRegisterOperand(
            ParserRuleContext operand) {
        return (CobolParser.SpecialRegisterContext)
                walkOperand(operand, StatementSerializer::isLengthOfSpecialRegister);
    }

    /** A {@code LENGTH OF} specialRegister — one whose LENGTH() token is present. */
    private static boolean isLengthOfSpecialRegister(org.antlr.v4.runtime.tree.ParseTree node) {
        return node instanceof CobolParser.SpecialRegisterContext
                && ((CobolParser.SpecialRegisterContext) node).LENGTH() != null;
    }

    /**
     * Serializes a referenceModifier context to a JsonObject with ref_mod_start
     * and optionally ref_mod_length (key absent when length is omitted in source).
     */
    private static JsonObject serializeRefMod(CobolParser.ReferenceModifierContext refMod) {
        JsonObject obj = new JsonObject();
        CobolParser.CharacterPositionContext charPos = refMod.characterPosition();
        obj.add("ref_mod_start",
            (charPos != null) ? serializeArithExprCtx(charPos.arithmeticExpression()) : litNode(""));
        CobolParser.LengthContext len = refMod.length();
        if (len != null) {
            obj.add("ref_mod_length",
                serializeArithExprCtx(len.arithmeticExpression()));
        }
        return obj;
    }

    /**
     * Serializes a MOVE operand Call to {name, ref_mod_start?, ref_mod_length?}.
     * ref_mod keys are absent (not null) when no reference modification is present.
     */
    private static JsonObject serializeMoveOperand(Call call) {
        // Unified structured-reference serializer (name + subscripts + ref-mod +
        // qualifiers). (red-dragon-6ddr)
        return serializeRef(call);
    }

    /**
     * Extracts the {@code OF}/{@code IN} qualifier data names for a Call (e.g.
     * {@code VSTRING-LENGTH OF WS-DATE-TO-TEST} -> ["WS-DATE-TO-TEST"]), in the
     * order written (immediate enclosing group first). COBOL allows duplicate
     * elementary names disambiguated by qualification (CardDemo CSUTLDTC's two
     * Vstring groups), and {@code extractCallName} returns only the leaf, so the
     * qualifiers are carried separately for the frontend to resolve against the
     * named ancestor group. Structural walk of the parse tree — no text parsing.
     */
    private static JsonArray extractQualifiers(Call call) {
        JsonArray qualifiers = new JsonArray();
        if (call == null) {
            return qualifiers;
        }
        Call unwrapped = call.unwrap();
        if (!(unwrapped instanceof ASGElementImpl)) {
            return qualifiers;
        }
        ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
        if (ctx == null) {
            return qualifiers;
        }
        collectInDataQualifiers(ctx, qualifiers);
        return qualifiers;
    }

    /**
     * Collects the {@code OF}/{@code IN} qualifier names written on an operand.
     *
     * <p>A qualifier arrives under one of two rules. Bare, it is an {@code inData}
     * ({@code FA OF GA}). Followed by a subscript or a reference modifier, ANTLR
     * takes the longer alternative and it is an {@code inTable} whose
     * {@code tableCall} carries both the group name and the parenthesised part —
     * {@code FA OF GA(1:2)} qualifies FA by GA exactly as the bare form does, so
     * both rules yield a qualifier here. Reading only {@code inData} dropped the
     * qualifier of every ref-modified or subscripted qualified operand, which then
     * resolved against the wrong group (red-dragon-64s4).
     *
     * <p>{@code FA OF GA(1:FB OF GB)} is qualified by GA and never by GB: names
     * written in a slice's bounds qualify the BOUND's own operand, which
     * {@link #walkOperand} enforces for every probe alike.
     */
    private static void collectInDataQualifiers(
            org.antlr.v4.runtime.tree.ParseTree node, JsonArray out) {
        walkOperand(node, n -> {
            addQualifierName(n, out);
            return false;
        });
    }

    /** Appends the qualifier name {@code node} writes, when it writes one. */
    private static void addQualifierName(
            org.antlr.v4.runtime.tree.ParseTree node, JsonArray out) {
        if (node instanceof CobolParser.InDataContext) {
            CobolParser.DataNameContext dn = ((CobolParser.InDataContext) node).dataName();
            if (dn != null) {
                out.add(dn.getText());
            }
        } else if (node instanceof CobolParser.InTableContext) {
            String base = tableCallBaseName(((CobolParser.InTableContext) node).tableCall());
            if (base != null) {
                out.add(base);
            }
        }
    }

    /**
     * Collects the subscripts ANTLR hung off a QUALIFIER's own {@code tableCall}.
     *
     * <p>{@code TB OF HT(I)} subscripts the whole reference — occurrence I of TB —
     * but the grammar takes the {@code inTable} alternative and {@code (I)} ends up
     * on HT's {@code tableCall}, where the operand's own subscript probes never look.
     * Both of them read occurrence 1 whatever I held (red-dragon-ds5t). This is the
     * subscript half of the {@code inTable} reading {@link #addQualifierName} owns
     * for the qualifier.
     *
     * <p>{@link #walkOperand} keeps a bound's subscripts out: the {@code (I)} in
     * {@code FA OF GA(1:TB OF HT(I))} is the bound's, never the slice's.
     */
    private static void collectInTableSubscripts(
            org.antlr.v4.runtime.tree.ParseTree node, JsonArray out) {
        walkOperand(node, n -> {
            addInTableSubscripts(n, out);
            return false;
        });
    }

    /** Appends the subscripts {@code node} writes on a qualifier, when it writes any. */
    private static void addInTableSubscripts(
            org.antlr.v4.runtime.tree.ParseTree node, JsonArray out) {
        if (!(node instanceof CobolParser.InTableContext)) {
            return;
        }
        CobolParser.TableCallContext tableCall = ((CobolParser.InTableContext) node).tableCall();
        if (tableCall == null) {
            return;
        }
        for (CobolParser.SubscriptContext sub : tableCall.subscript()) {
            out.add(serializeSubscriptCtx(sub));
        }
    }

    /** The bare data name a {@code tableCall} is built on, stripped of subscripts
     *  and reference modification, or null when it has none. */
    private static String tableCallBaseName(CobolParser.TableCallContext tableCall) {
        if (tableCall == null || tableCall.qualifiedDataName() == null) {
            return null;
        }
        CobolParser.QualifiedDataNameFormat1Context format1 =
                tableCall.qualifiedDataName().qualifiedDataNameFormat1();
        if (format1 == null || format1.dataName() == null) {
            return null;
        }
        return format1.dataName().getText();
    }


    /**
     * Serializes an arithmetic source operand ValueStmt.
     * Returns a JsonElement: either a JsonObject with {name, ref_mod_start?, ref_mod_length?}
     * for Call-based operands, or a string for literals.
     */
    private static JsonElement serializeArithSource(ValueStmt vs) {
        if (vs instanceof CallValueStmt) {
            Call c = ((CallValueStmt) vs).getCall();
            JsonObject fn = serializeFunctionNode(c);
            if (fn != null) {
                return fn;
            }
            return serializeMoveOperand(c);
        }
        if (vs instanceof LiteralValueStmt) {
            JsonObject dfh = serializeDfhrespLit((LiteralValueStmt) vs);
            if (dfh != null) return dfh;
        }
        // For literals and other operands, return as plain string
        if (vs != null && isNumericLiteral(vs.getCtx())) {
            JsonObject literal = new JsonObject();
            literal.addProperty("name", extractValueStmtText(vs));
            literal.addProperty("numeric", true);
            return literal;
        }
        return new JsonPrimitive(extractValueStmtText(vs));
    }

    /**
     * Locates the {@link CobolParser.FunctionCallContext} reachable from a Call's
     * grammar context, if any. COBOL intrinsic functions (FUNCTION UPPER-CASE(...))
     * surface as a FUNCTION_CALL whose ctx is — or contains — a FunctionCallContext.
     *
     * @return the FunctionCallContext, or {@code null} when the call is not a function.
     */
    private static CobolParser.FunctionCallContext findFunctionCallCtx(Call call) {
        if (call == null) {
            return null;
        }
        Call unwrapped = call.unwrap();
        if (!(unwrapped instanceof ASGElementImpl)) {
            return null;
        }
        ParserRuleContext ctx = ((ASGElementImpl) unwrapped).getCtx();
        return findFunctionCallCtx(ctx);
    }

    /**
     * Walks a grammar context (and its ancestors/descendants) to find a
     * FunctionCallContext. ProLeap may attach the call to an identifier-shaped
     * context whose subtree (or parent) holds the actual functionCall rule.
     *
     * <p>A call found below a referenceModifier of {@code ctx} is NOT returned:
     * it computes a slice bound, not the operand. See {@link #walkOperand}.
     */
    private static CobolParser.FunctionCallContext findFunctionCallCtx(ParserRuleContext ctx) {
        if (ctx == null) {
            return null;
        }
        if (ctx instanceof CobolParser.FunctionCallContext) {
            return (CobolParser.FunctionCallContext) ctx;
        }
        // Search ancestors (the Call ctx may be a child of the functionCall rule).
        for (ParserRuleContext p = ctx.getParent(); p != null; p = p.getParent()) {
            if (p instanceof CobolParser.FunctionCallContext) {
                return (CobolParser.FunctionCallContext) p;
            }
        }
        // Search descendants (the functionCall rule may be nested under ctx).
        CobolParser.FunctionCallContext direct =
                ctx.getRuleContext(CobolParser.FunctionCallContext.class, 0);
        return (direct != null) ? direct : findFunctionCallCtxInSubtree(ctx);
    }

    /**
     * Finds a FunctionCallContext at {@code ctx} itself or among its descendants
     * ONLY (never ancestors). Used when serializing a basis operand: a basis that
     * IS a function call must serialize structurally, but a basis that is a plain
     * ref nested inside a larger function call must NOT be mistaken for one.
     *
     * <p>A call found below a referenceModifier of {@code ctx} is NOT returned:
     * it computes a slice bound, not the operand. See {@link #walkOperand}.
     */
    private static CobolParser.FunctionCallContext findFunctionCallCtxInSubtree(ParserRuleContext ctx) {
        return (CobolParser.FunctionCallContext)
                walkOperand(ctx, n -> n instanceof CobolParser.FunctionCallContext);
    }


    /**
     * Serializes a COBOL intrinsic FUNCTION call to a structured node:
     * {@code {"kind":"function","name":"UPPER-CASE","args":[<operand>, ...]}}.
     *
     * <p>The function name and arguments are read from the grammar context for
     * fidelity (ProLeap models the call as a thin marker without structured args).
     * Each argument is serialized with the existing operand/expression serializers.
     *
     * @return the function node, or {@code null} when {@code call} is not a function call.
     */
    /**
     * Like {@link #serializeFunctionNode(Call)} but probes a ValueStmt's own
     * grammar context. Some intrinsic forms (notably the no-argument
     * FUNCTION CURRENT-DATE) do not surface as a CallValueStmt; the functionCall
     * rule is reachable from the ValueStmt's ctx instead.
     */
    private static JsonObject serializeFunctionNodeFromValueStmt(ValueStmt vs) {
        if (vs == null) {
            return null;
        }
        ParserRuleContext ctx = vs.getCtx();
        CobolParser.FunctionCallContext fc = findFunctionCallCtx(ctx);
        return serializeFunctionNodeFromCtx(fc);
    }

    private static JsonObject serializeFunctionNode(Call call) {
        CobolParser.FunctionCallContext fc = findFunctionCallCtx(call);
        return serializeFunctionNodeFromCtx(fc);
    }

    private static JsonObject serializeFunctionNodeFromCtx(CobolParser.FunctionCallContext fc) {
        if (fc == null) {
            return null;
        }
        JsonObject obj = new JsonObject();
        obj.addProperty("kind", "function");
        String name = (fc.functionName() != null) ? fc.functionName().getText() : "";
        obj.addProperty("name", name.toUpperCase());
        JsonArray args = new JsonArray();
        for (JsonElement arg : serializeFunctionArguments(fc)) {
            args.add(arg);
        }
        obj.add("args", args);
        return obj;
    }

    /** Arguments of a functionCall, one per argument the grammar parsed. */
    private static List<JsonElement> serializeFunctionArguments(
            CobolParser.FunctionCallContext fc) {
        List<JsonElement> args = new ArrayList<>();
        for (CobolParser.ArgumentContext arg : fc.argument()) {
            args.add(serializeFunctionArg(arg));
        }
        return args;
    }

    /**
     * Serializes a single intrinsic-function argument to an expression node,
     * reusing the arithmetic-expression serializer for fidelity. Falls back to a
     * plain ref/literal node when no arithmeticExpression sub-rule is present.
     */
    private static JsonElement serializeFunctionArg(CobolParser.ArgumentContext arg) {
        if (arg == null) {
            return litNode("");
        }
        // Every argument is now an arithmeticExpression (grammar:
        // argument : arithmeticExpression | qualifiedDataName ... | indexName ...).
        // serializeArithExprCtx -> ... -> serializeBasisCtx recursively handles
        // nested FUNCTION calls (red-dragon-ge72), reference modification
        // (red-dragon-74qu), LENGTH OF, figuratives, and builds the +/- and */÷
        // binop tree. So an arithmetic argument like F(a - 1) serialises as a
        // binop with the nested function inside it, instead of being collapsed to
        // just its inner function (red-dragon-zgwl). No subtree short-circuit.
        if (arg.arithmeticExpression() != null) {
            return serializeArithExprCtx(arg.arithmeticExpression());
        }
        if (arg.qualifiedDataName() != null) {
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            ref.addProperty("name", arg.qualifiedDataName().getText());
            return ref;
        }
        return litNode(arg.getText(), arg);
    }

    /**
     * Extracts text from a ValueStmt, falling back to ANTLR context getText().
     */
    static String extractValueStmtText(ValueStmt vs) {
        if (vs == null) {
            return "";
        }
        try {
            if (vs.getCtx() != null) {
                return vs.getCtx().getText();
            }
        } catch (Exception e) {
            // fall through
        }
        return vs.toString();
    }

    /**
     * Serializes a ConditionValueStmt as written: its first combinable condition,
     * then each AND/OR link in order.
     *
     * <p>{@code {"first": <atom>, "rest": [{"bool": "AND"|"OR", "atom": <atom>}
     * | {"bool": ..., "abbreviations": [{"not": bool, "op"?: op, "right": <expr>}]}]}}.
     * An abbreviation's {@code "op"} is absent when it states none. The ASG
     * reader (cobol_asg/abbreviated_condition.py) applies precedence and the
     * implied subject and operator.
     */
    private static JsonObject serializeConditionNode(ConditionValueStmt cond) {
        JsonObject written = new JsonObject();
        written.add("first", serializeCombinableCondition(cond.getCombinableCondition()));
        JsonArray rest = new JsonArray();
        for (AndOrCondition aoc : cond.getAndOrConditions()) {
            JsonObject link = new JsonObject();
            link.addProperty("bool",
                    aoc.getAndOrConditionType() == AndOrCondition.AndOrConditionType.AND ? "AND" : "OR");
            if (aoc.getCombinableCondition() != null) {
                link.add("atom", serializeCombinableCondition(aoc.getCombinableCondition()));
            } else {
                link.add("abbreviations", serializeAbbreviations(aoc));
            }
            rest.add(link);
        }
        written.add("rest", rest);
        return written;
    }

    private static JsonArray serializeAbbreviations(AndOrCondition aoc) {
        JsonArray written = new JsonArray();
        if (aoc.getAbbreviations() == null) {
            return written;
        }
        for (io.proleap.cobol.asg.metamodel.valuestmt.relation.Abbreviation abbr : aoc.getAbbreviations()) {
            CobolParser.AbbreviationContext ctx = (CobolParser.AbbreviationContext) abbr.getCtx();
            JsonObject abbreviation = new JsonObject();
            abbreviation.addProperty("not", ctx.NOT() != null);
            if (abbr.getOperator() != null) {
                abbreviation.addProperty("op", relationalOpToString(abbr.getOperator()));
            }
            abbreviation.add("right", abbr.getArithmeticExpression() != null
                    ? serializeArithmeticExpr(abbr.getArithmeticExpression()) : litNode(""));
            written.add(abbreviation);
        }
        return written;
    }

    /**
     * Serializes a single CombinableCondition (one atom, possibly negated).
     *
     * <p>Result shapes:
     * <ul>
     *   <li>{@code {"not": bool, "condition_name": "IS-MINOR"}} for 88-level references,
     *       with {@code condition_qualifiers} for its OF/IN qualifiers and
     *       {@code condition_subscripts} for its subscripts when written</li>
     *   <li>{@code {"not": bool, "data_operand": <ref>}} for a name written as a condition
     *       that resolves to a data item: an abbreviated operand</li>
     *   <li>{@code {"not": bool, "relation": {"left": <expr>, "op": "...", "right": <expr>}}} for relation conditions</li>
     *   <li>{@code {"not": bool, "text": "..."}} fallback for class/sign/unknown conditions</li>
     *   <li>{@code {"not": bool, "condition": {...}}} for nested parenthesised conditions</li>
     *   <li>{@code {"not": bool, "combined": {...}}} for a combined relation {@code A = (X OR Y)}</li>
     * </ul>
     */
    private static JsonObject serializeCombinableCondition(CombinableCondition cc) {
        JsonObject obj = new JsonObject();
        if (cc == null) {
            obj.addProperty("text", "");
            return obj;
        }
        boolean not = cc.isNot();
        obj.addProperty("not", not);

        SimpleCondition sc = cc.getSimpleCondition();
        if (sc == null) {
            obj.addProperty("text", "");
            return obj;
        }

        SimpleCondition.SimpleConditionType scType = sc.getSimpleConditionType();
        if (scType == SimpleCondition.SimpleConditionType.CONDITION_NAME_REFERENCE) {
            ConditionNameReference ref = sc.getConditionNameReference();
            if (ref != null && namesDataItem(ref.getConditionCall())) {
                obj.add("data_operand", dataOperand(ref));
            } else if (ref != null && ref.getConditionCall() != null) {
                obj.addProperty("condition_name", extractCallName(ref.getConditionCall()));
                JsonArray conditionSubscripts = extractConditionSubscripts(ref);
                if (conditionSubscripts.size() > 0) {
                    obj.add("condition_subscripts", conditionSubscripts);
                }
                JsonArray conditionQualifiers = new JsonArray();
                collectInDataQualifiers(ref.getCtx(), conditionQualifiers);
                if (conditionQualifiers.size() > 0) {
                    obj.add("condition_qualifiers", conditionQualifiers);
                }
            } else {
                obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            }
        } else if (scType == SimpleCondition.SimpleConditionType.CONDITION) {
            ConditionValueStmt nested = sc.getCondition();
            if (nested != null) {
                obj.add("condition", serializeConditionNode(nested));
            } else {
                obj.addProperty("text", "");
            }
        } else if (scType == SimpleCondition.SimpleConditionType.RELATION_CONDITION) {
            RelationConditionValueStmt rel = sc.getRelationCondition();
            if (rel == null) {
                obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            } else if (rel.getRelationConditionType()
                    == RelationConditionValueStmt.RelationConditionType.COMBINED) {
                JsonObject combined = serializeCombinedComparison(rel.getCombinedComparison());
                if (combined != null) {
                    obj.add("combined", combined);
                } else {
                    obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
                }
            } else if (rel.getRelationConditionType()
                    == RelationConditionValueStmt.RelationConditionType.SIGN) {
                serializeSignCondition(obj, sc, not);
            } else {
                obj.add("relation", serializeRelationCondition(rel));
            }
        } else if (scType == SimpleCondition.SimpleConditionType.CLASS_CONDITION) {
            serializeClassCondition(obj, sc, not);
        } else {
            // Unknown — fall back to text
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
        }

        return obj;
    }

    /**
     * Populates {@code obj} for a CLASS_CONDITION, emitting the structured
     * {@code {"not": bool, "class": "NUMERIC"|..., "operand": <expr>}} shape.
     *
     * <p>COBOL {@code X IS NOT NUMERIC} may carry the negation on the enclosing
     * CombinableCondition ({@code ccNot}) and/or the ClassCondition itself; the
     * effective negation is their XOR. If the class type or operand is not
     * supported, falls back to the existing text path for this node only.
     */
    private static void serializeClassCondition(JsonObject obj, SimpleCondition sc, boolean ccNot) {
        ClassCondition cls = sc.getClassCondition();
        if (cls == null) {
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            return;
        }
        if (cls.getClassConditionType() == ClassCondition.ClassConditionType.CLASS_NAME
                && cls.getIdentifierCall() != null
                && cls.getCtx() instanceof CobolParser.ClassConditionContext ctx
                && ctx.className() != null) {
            obj.addProperty("not", ccNot ^ cls.getNot());
            obj.addProperty("class_name", ctx.className().getText().toUpperCase());
            JsonObject operand = serializeMoveOperand(cls.getIdentifierCall());
            operand.addProperty("kind", "ref");
            obj.add("operand", operand);
            return;
        }
        String className = classConditionTypeToString(cls.getClassConditionType());
        if (className == null || cls.getIdentifierCall() == null) {
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            return;
        }
        boolean effectiveNot = ccNot ^ cls.getNot();
        obj.addProperty("not", effectiveNot);
        obj.addProperty("class", className);
        // The operand may be reference-modified, e.g.
        // WS-FIELD(1:WS-LEN) IS NUMERIC. serializeMoveOperand captures both the
        // name and any ref_mod_start/ref_mod_length so the class test runs over
        // the slice, not the whole space-padded field (red-dragon-zuhj).
        JsonObject operand = serializeMoveOperand(cls.getIdentifierCall());
        operand.addProperty("kind", "ref");
        obj.add("operand", operand);
    }

    /** Maps a ProLeap class-condition type to its canonical condition string, or null if unsupported. */
    private static String classConditionTypeToString(ClassCondition.ClassConditionType type) {
        if (type == null) {
            return null;
        }
        switch (type) {
            case NUMERIC:
                return "NUMERIC";
            case ALPHABETIC:
                return "ALPHABETIC";
            case ALPHABETIC_LOWER:
                return "ALPHABETIC-LOWER";
            case ALPHABETIC_UPPER:
                return "ALPHABETIC-UPPER";
            default:
                return null;
        }
    }

    /**
     * Populates {@code obj} for a SIGN relation condition (IF x IS POSITIVE /
     * NEGATIVE / ZERO), emitting the structured
     * {@code {"not": bool, "sign": "POSITIVE"|"NEGATIVE"|"ZERO", "operand": <expr>}}
     * shape — mirroring class conditions. The effective negation is the XOR of the
     * enclosing CombinableCondition's {@code not} and the sign condition's own
     * {@code not}. Falls back to the text path for this node only if unsupported.
     */
    private static void serializeSignCondition(JsonObject obj, SimpleCondition sc, boolean ccNot) {
        SignCondition sign = sc.getRelationCondition() != null
                ? sc.getRelationCondition().getSignCondition()
                : null;
        String signStr = sign != null ? signConditionTypeToString(sign.getSignConditionType()) : null;
        if (sign == null || signStr == null || sign.getArithmeticExpression() == null) {
            obj.addProperty("text", insertSpaces(sc.getCtx().getText()));
            return;
        }
        boolean effectiveNot = ccNot ^ sign.getNot();
        obj.addProperty("not", effectiveNot);
        obj.addProperty("sign", signStr);
        obj.add("operand", serializeArithmeticExpr(sign.getArithmeticExpression()));
    }

    /** Maps a ProLeap sign-condition type to its canonical string, or null if unsupported. */
    private static String signConditionTypeToString(SignCondition.SignConditionType type) {
        if (type == null) {
            return null;
        }
        switch (type) {
            case POSITIVE:
                return "POSITIVE";
            case NEGATIVE:
                return "NEGATIVE";
            case ZERO:
                return "ZERO";
            default:
                return null;
        }
    }

    /**
     * Serializes a RELATION_CONDITION to {"left": <expr>, "op": "...", "right": <expr>}.
     * Falls back to {"text": "..."} for SIGN and COMBINED condition types.
     */
    private static JsonObject serializeRelationCondition(RelationConditionValueStmt rel) {
        JsonObject obj = new JsonObject();
        if (rel.getRelationConditionType() == RelationConditionValueStmt.RelationConditionType.ARITHMETIC) {
            ArithmeticComparison ac = rel.getArithmeticComparison();
            if (ac != null) {
                obj.add("left", ac.getArithmeticExpressionLeft() != null
                        ? serializeArithmeticExpr(ac.getArithmeticExpressionLeft())
                        : litNode(""));
                obj.addProperty("op", relationalOpToString(ac.getOperator()));
                obj.add("right", ac.getArithmeticExpressionRight() != null
                        ? serializeArithmeticExpr(ac.getArithmeticExpressionRight())
                        : litNode(""));
                return obj;
            }
        }
        // SIGN — not yet structured; fall back to text (deferred).
        obj.addProperty("text", rel.getCtx() != null ? insertSpaces(rel.getCtx().getText()) : "");
        return obj;
    }

    /**
     * Serializes a COMBINED relation {@code A = (X OR Y)} as written:
     * {@code {"left": A, "op": op, "bool": "AND"|"OR", "operands": [X, Y]}}.
     * The ASG reader expands it.
     *
     * @return the written relation, or {@code null} if a part is missing
     *         (caller falls back to text).
     */
    private static JsonObject serializeCombinedComparison(CombinedComparison cc) {
        if (cc == null) {
            return null;
        }
        ArithmeticValueStmt subject = cc.getArithmeticExpression();
        CombinedCondition combined = cc.getCombinedCondition();
        if (subject == null || combined == null) {
            return null;
        }
        List<ArithmeticValueStmt> operands = combined.getArithmeticExpressions();
        if (operands == null || operands.isEmpty()) {
            return null;
        }
        JsonObject written = new JsonObject();
        written.add("left", serializeArithmeticExpr(subject));
        written.addProperty("op", relationalOpToString(cc.getOperator()));
        written.addProperty("bool", (combined.getCombinedConditionType()
                == CombinedCondition.CombinedConditionType.AND) ? "AND" : "OR");
        JsonArray right = new JsonArray();
        for (ArithmeticValueStmt operand : operands) {
            right.add(serializeArithmeticExpr(operand));
        }
        written.add("operands", right);
        return written;
    }

    private static String relationalOpToString(RelationalOperator op) {
        if (op == null) return "==";
        switch (op.getRelationalOperatorType()) {
            case EQUAL: return "==";
            case GREATER: return ">";
            case GREATER_OR_EQUAL: return ">=";
            case LESS: return "<";
            case LESS_OR_EQUAL: return "<=";
            case NOT_EQUAL: return "!=";
            default: return "==";
        }
    }

    /**
     * Serializes an ArithmeticValueStmt as a left-folded expression tree.
     * Returns one of: {"kind":"ref","name":"..."}, {"kind":"lit","value":"..."},
     * {"kind":"binop","op":"...","left":<expr>,"right":<expr>},
     * {"kind":"neg","expr":<expr>}.
     */
    private static JsonElement serializeArithmeticExpr(ArithmeticValueStmt avs) {
        if (avs == null) return litNode("");
        JsonElement result = serializeMultDivs(avs.getMultDivs());
        for (PlusMinus pm : avs.getPlusMinus()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", pm.getPlusMinusType() == PlusMinus.PlusMinusType.PLUS ? "+" : "-");
            binop.add("left", result);
            binop.add("right", serializeMultDivs(pm.getMultDivs()));
            result = binop;
        }
        return result;
    }

    private static JsonElement serializeMultDivs(MultDivs md) {
        if (md == null) return litNode("");
        JsonElement result = serializePowers(md.getPowers());
        for (MultDiv mdo : md.getMultDivs()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", mdo.getMultDivType() == MultDiv.MultDivType.MULT ? "*" : "/");
            binop.add("left", result);
            binop.add("right", serializePowers(mdo.getPowers()));
            result = binop;
        }
        return result;
    }

    private static JsonElement serializePowers(Powers p) {
        if (p == null) return litNode("");
        JsonElement result = serializeBasis(p.getBasis());
        // Exponentiation (**): chain each power operand as a nested binop node.
        for (io.proleap.cobol.asg.metamodel.valuestmt.arithmetic.Power exp : p.getPowers()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", "**");
            binop.add("left", result);
            binop.add("right", serializeBasis(exp.getBasis()));
            result = binop;
        }
        if (p.getPowersType() == Powers.PowersType.MINUS) {
            JsonObject neg = new JsonObject();
            neg.addProperty("kind", "neg");
            neg.add("expr", result);
            return neg;
        }
        return result;
    }

    /**
     * True when a basis is the parenthesised alternative of
     * {@code basis : LPARENCHAR arithmeticExpression RPARENCHAR | identifier | literal}
     * — a whole sub-expression in parentheses, whose contents belong to the
     * expression, not to the basis.
     */
    private static boolean parenthesisedBasis(ParserRuleContext ctx) {
        return ctx instanceof CobolParser.BasisContext
                && ((CobolParser.BasisContext) ctx).arithmeticExpression() != null;
    }

    private static JsonElement serializeBasis(Basis b) {
        if (b == null) return litNode("");
        // Intrinsic FUNCTION call as a basis (e.g. inside an IF relation:
        // FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B)). ProLeap surfaces the
        // basis as a CallValueStmt whose extractCallName collapses to just the
        // function NAME (dropping the call + args). Probe the basis's own grammar
        // subtree (self + descendants, NOT ancestors) for a functionCall rule and
        // emit the structured {"kind":"function","name":..,"args":[..]} node — the
        // same shape MOVE/arithmetic already produce (red-dragon-ge72).
        //
        // A PARENTHESISED basis is excluded: its subtree holds a whole
        // sub-expression, and any FUNCTION inside it is one operand of that
        // sub-expression, not the basis itself. Probing it returned the nested
        // call as the entire group and silently discarded every other operand
        // and operator — `(FUNCTION LENGTH(M) - N)` computed LENGTH(M)
        // (red-dragon-84k). Such a basis falls through to the
        // ArithmeticValueStmt branch, which recurses and reaches the function
        // through the operand that actually is one.
        CobolParser.FunctionCallContext fnCtx =
                parenthesisedBasis(b.getCtx()) ? null : findFunctionCallCtxInSubtree(b.getCtx());
        if (fnCtx != null) {
            JsonObject fn = serializeFunctionNodeFromCtx(fnCtx);
            if (fn != null) {
                return fn;
            }
        }
        ValueStmt vs = b.getBasisValueStmt();
        if (vs instanceof CallValueStmt) {
            Call call = ((CallValueStmt) vs).getCall();
            Call addressed = addressOfTarget(call);
            if (addressed != null) {
                return operandRef(addressed, "address_of");
            }
            // LENGTH OF <item> as an arithmetic operand (COMPUTE L = LENGTH OF G + 1)
            // is the item's length, not a data item named LENGTH (red-dragon-sl30.53).
            Call measured = lengthOfTarget(call);
            if (measured != null) {
                JsonObject measuredRef = serializeRef(measured);
                JsonObject lengthOf = new JsonObject();
                lengthOf.addProperty("kind", "length_of");
                lengthOf.add("name", measuredRef.get("name"));
                if (measuredRef.has("qualifiers")) {
                    lengthOf.add("qualifiers", measuredRef.get("qualifiers"));
                }
                return lengthOf;
            }
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            if (call != null) {
                // Structured subscriptable reference (name + subscripts + ref-mod
                // + qualifiers). (red-dragon-6ddr)
                JsonObject struct = serializeRef(call);
                for (String key : struct.keySet()) {
                    ref.add(key, struct.get(key));
                }
            } else {
                ref.addProperty("name", b.getCtx().getText());
            }
            return ref;
        }
        if (vs instanceof ArithmeticValueStmt) {
            // Parenthesised sub-expression
            return serializeArithmeticExpr((ArithmeticValueStmt) vs);
        }
        if (vs instanceof LiteralValueStmt) {
            JsonObject dfh = serializeDfhrespLit((LiteralValueStmt) vs);
            if (dfh != null) return dfh;
            Literal lit = ((LiteralValueStmt) vs).getLiteral();
            if (lit != null && allRepeatedLiteral(lit.getCtx()) != null) {
                return allLiteralNode(allRepeatedLiteral(lit.getCtx()));
            }
            if (lit != null && lit.getLiteralType() == Literal.LiteralType.FIGURATIVE_CONSTANT
                    && lit.getFigurativeConstant() != null) {
                String canonical = canonicalFigurative(lit.getFigurativeConstant().getFigurativeConstantType());
                if (canonical != null) {
                    JsonObject fig = new JsonObject();
                    fig.addProperty("kind", "figurative");
                    fig.addProperty("value", canonical);
                    return fig;
                }
            }
        }
        // Literals (LiteralValueStmt, IntegerLiteralValueStmt, etc.)
        ParserRuleContext textCtx = vs != null && vs.getCtx() != null ? vs.getCtx() : b.getCtx();
        return litNode(textCtx != null ? textCtx.getText() : "", textCtx);
    }

    /**
     * If {@code lvs} carries a {@code CICS_DFH_RESP} literal, returns a structured
     * {@code {"kind":"dfhresp","condition":"<NAME>"}} node; otherwise returns null.
     * Used by serializeBasis, serializeArithSource, serializeMove, and serializeEvaluate
     * so DFHRESP(X) is never emitted as a raw text string (red-dragon-kieo).
     */
    private static JsonObject serializeDfhrespLit(LiteralValueStmt lvs) {
        if (lvs == null) return null;
        Literal lit = lvs.getLiteral();
        if (lit == null || lit.getLiteralType() != Literal.LiteralType.CICS_DFH_RESP) return null;
        if (!(lit.getCtx() instanceof CobolParser.LiteralContext)) return null;
        CobolParser.CicsDfhRespLiteralContext dfhCtx =
            ((CobolParser.LiteralContext) lit.getCtx()).cicsDfhRespLiteral();
        String cond = (dfhCtx != null && dfhCtx.cobolWord() != null)
            ? dfhCtx.cobolWord().getText().toUpperCase() : "";
        JsonObject obj = new JsonObject();
        obj.addProperty("kind", "dfhresp");
        obj.addProperty("condition", cond);
        return obj;
    }

    /**
     * Emit a dfhresp node when vs is a LiteralValueStmt with CICS_DFH_RESP type.
     *
     * With the grammar fix (literal before identifier in basis and evaluateValue),
     * DFHRESP(X) always parses as LiteralValueStmt in every context (red-dragon-kieo).
     * Returns null when vs is not a DFHRESP literal.
     */
    private static JsonObject serializeDfhrespFromVS(ValueStmt vs) {
        if (vs instanceof LiteralValueStmt) {
            return serializeDfhrespLit((LiteralValueStmt) vs);
        }
        return null;
    }

    // ── Grammar-context arithmetic serializers (for referenceModifier) ──────────

    /**
     * Grammar: arithmeticExpression : multDivs plusMinus*
     * plusMinus : (PLUSCHAR | MINUSCHAR) multDivs
     * Note: ctx.multDivs() is SINGULAR (not a list); ctx.plusMinus() is a List.
     */
    private static JsonElement serializeArithExprCtx(CobolParser.ArithmeticExpressionContext ctx) {
        if (ctx == null) return litNode("");
        JsonElement result = serializeMultDivsCtx(ctx.multDivs());
        for (CobolParser.PlusMinusContext pm : ctx.plusMinus()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", pm.PLUSCHAR() != null ? "+" : "-");
            binop.add("left", result);
            binop.add("right", serializeMultDivsCtx(pm.multDivs()));
            result = binop;
        }
        return result;
    }

    /**
     * Grammar: multDivs : powers multDiv*
     * multDiv : (ASTERISKCHAR | SLASHCHAR) powers
     * Note: ctx.powers() is SINGULAR; ctx.multDiv() is a List.
     */
    private static JsonElement serializeMultDivsCtx(CobolParser.MultDivsContext ctx) {
        if (ctx == null) return litNode("");
        JsonElement result = serializePowersCtx(ctx.powers());
        for (CobolParser.MultDivContext md : ctx.multDiv()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", md.ASTERISKCHAR() != null ? "*" : "/");
            binop.add("left", result);
            binop.add("right", serializePowersCtx(md.powers()));
            result = binop;
        }
        return result;
    }

    /**
     * Grammar: powers : (PLUSCHAR | MINUSCHAR)? basis power*
     * power : DOUBLEASTERISKCHAR basis
     * Note: ctx.basis() is SINGULAR; ctx.power() is a List.
     */
    private static JsonElement serializePowersCtx(CobolParser.PowersContext ctx) {
        if (ctx == null) return litNode("");
        JsonElement result = serializeBasisCtx(ctx.basis());
        for (CobolParser.PowerContext p : ctx.power()) {
            JsonObject binop = new JsonObject();
            binop.addProperty("kind", "binop");
            binop.addProperty("op", "**");
            binop.add("left", result);
            binop.add("right", serializeBasisCtx(p.basis()));
            result = binop;
        }
        if (ctx.MINUSCHAR() != null) {
            JsonObject neg = new JsonObject();
            neg.addProperty("kind", "neg");
            neg.add("expr", result);
            return neg;
        }
        return result;
    }

    /**
     * Returns the LEAF data-name of an identifier, dropping OF/IN qualification.
     *
     * COBOL `FLD-A OF GRP-B` is one field named the qualified way; red-dragon
     * resolves data items by leaf name, so we emit "FLD-A" (the first dataName of
     * qualifiedDataNameFormat1) rather than the flattened parse-tree text
     * "FLD-AOFGRP-B" that getText() would produce. Falls back to getText() for
     * non-qualifiedDataName identifiers (tableCall / functionCall / specialRegister).
     */
    private static CobolParser.QualifiedDataNameFormat1Context
            findQualifiedDataNameFormat1(org.antlr.v4.runtime.tree.ParseTree node) {
        return (CobolParser.QualifiedDataNameFormat1Context)
                walkOperand(node, n -> n instanceof CobolParser.QualifiedDataNameFormat1Context);
    }

    private static String leafDataName(CobolParser.IdentifierContext id) {
        if (id == null) {
            return "";
        }
        CobolParser.QualifiedDataNameContext qdn = id.qualifiedDataName();
        if (qdn != null) {
            CobolParser.QualifiedDataNameFormat1Context f1 = qdn.qualifiedDataNameFormat1();
            if (f1 != null && f1.dataName() != null) {
                return f1.dataName().getText();
            }
        }
        return id.getText();
    }

    /**
     * Bare base data-name of an identifier, with any reference-modifier suffix
     * stripped. {@link #leafDataName} falls back to {@code id.getText()} when the
     * qualifiedDataName carries a referenceModifier (its {@code dataName()} is then
     * null), which would glue the {@code (start:len)} slice into the name — an
     * unresolvable field. This searches structurally for the underlying
     * qualifiedDataNameFormat1's dataName instead. (red-dragon-74qu)
     */
    private static String baseDataName(CobolParser.IdentifierContext id) {
        if (id == null) {
            return "";
        }
        CobolParser.QualifiedDataNameFormat1Context f1 = findQualifiedDataNameFormat1(id);
        if (f1 != null && f1.dataName() != null) {
            return f1.dataName().getText();
        }
        return leafDataName(id);
    }

    /**
     * Serializes an identifier that MAY carry a reference modifier into a
     * structured ref node: {@code {kind:ref, name:<bare base>, ref_mod_start,
     * ref_mod_length?}}. Mirrors {@link #serializeRef}'s ref-mod handling for the
     * grammar-context paths (function args, arithmetic basis) that operate on an
     * IdentifierContext rather than a Call. Returns {@code null} when the
     * identifier carries no reference modifier (caller emits a plain ref).
     * (red-dragon-74qu)
     */
    private static JsonObject serializeRefModIdentifier(CobolParser.IdentifierContext id) {
        if (id == null) {
            return null;
        }
        CobolParser.ReferenceModifierContext refMod = firstReferenceModifierDescendant(id);
        if (refMod == null) {
            return null;
        }
        JsonObject ref = new JsonObject();
        ref.addProperty("kind", "ref");
        ref.addProperty("name", baseDataName(id));
        JsonObject rm = serializeRefMod(refMod);
        ref.add("ref_mod_start", rm.get("ref_mod_start"));
        if (rm.has("ref_mod_length")) {
            ref.add("ref_mod_length", rm.get("ref_mod_length"));
        }
        addCtxQualifiers(ref, id);
        return ref;
    }

    /**
     * Adds the {@code OF}/{@code IN} qualifiers a grammar-context operand writes,
     * the way {@link #serializeRef} adds a Call's.
     *
     * <p>The ctx-side serializers emitted the leaf name alone, so every expression
     * position they cover — a FUNCTION argument, an arithmetic basis, a subscript,
     * a slice bound — resolved a duplicated name against whichever group won,
     * or raised (red-dragon-2afo). {@link #collectInDataQualifiers} reads both
     * spellings of a qualifier and stops at a reference modifier, so a bound's
     * own qualifier stays the bound's.
     */
    private static void addCtxQualifiers(
            JsonObject ref, org.antlr.v4.runtime.tree.ParseTree operand) {
        JsonArray qualifiers = new JsonArray();
        collectInDataQualifiers(operand, qualifiers);
        if (qualifiers.size() > 0) {
            ref.add("qualifiers", qualifiers);
        }
    }

    /**
     * Grammar: basis : LPARENCHAR arithmeticExpression RPARENCHAR | identifier | literal
     * Note: ctx.arithmeticExpression() is non-null for parenthesised sub-expressions.
     */
    private static JsonElement serializeBasisCtx(CobolParser.BasisContext ctx) {
        if (ctx == null) return litNode("");
        if (ctx.arithmeticExpression() != null) {
            return serializeArithExprCtx(ctx.arithmeticExpression());
        }
        CobolParser.IdentifierContext id = ctx.identifier();
        if (id != null) {
            return serializeIdentifierCtx(id);
        }
        return serializeLiteralCtx(ctx.literal());
    }

    /**
     * An identifier operand as a structured expression node: a FUNCTION call,
     * {@code LENGTH OF}, or a ref carrying its subscripts, slice and qualifiers.
     */
    private static JsonElement serializeIdentifierCtx(CobolParser.IdentifierContext id) {
        // Nested intrinsic FUNCTION as a basis (e.g. FUNCTION UPPER-CASE(FUNCTION
        // TRIM(x))). ProLeap surfaces the inner function as an identifier whose
        // subtree holds the functionCall rule; without this probe it serializes
        // as the bare function NAME ref ("TRIM"). Emit the structured function
        // node so the call + args survive (red-dragon-ge72).
        CobolParser.FunctionCallContext fnCtx = findFunctionCallCtxInSubtree(id);
        if (fnCtx != null) {
            JsonObject fn = serializeFunctionNodeFromCtx(fnCtx);
            if (fn != null) {
                return fn;
            }
        }
        if (id != null) {
            // LENGTH OF <field> surfaces as an identifier wrapping a
            // specialRegister; getText() would glue it into "LENGTHOF<field>"
            // (an unresolvable name the frontend treats as 0). Emit a structured
            // length_of node so the frontend resolves the field's byte length —
            // matching serializeFromValue's PERFORM-VARYING handling. (oq2c)
            CobolParser.SpecialRegisterContext sr = lengthOfSpecialRegisterOperand(id);
            if (sr != null) {
                return lengthOfNode(sr.identifier());
            }
            // OCCURS subscripts on a grammar-context identifier. The ASG-based
            // serializer emits these via extractSubscripts/serializeRef; this path
            // dropped them entirely, so every FUNCTION f(TBL(I)) read occurrence 1
            // and a multi-dimension TBL(I, J) arrived as the unresolvable name
            // "TBL(IJ)" (red-dragon-jscx).
            JsonArray subscripts = serializeIdentifierSubscripts(id);
            // A reference-modified identifier (e.g. WS-FLD(1:LEN)) must keep its
            // slice structured so the frontend resolves the base field and the
            // start/length, rather than gluing them into an unresolvable name.
            // (red-dragon-74qu)
            JsonObject refMod = serializeRefModIdentifier(id);
            if (refMod != null) {
                if (subscripts.size() > 0) {
                    refMod.add("subscripts", subscripts);
                }
                return refMod;
            }
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            if (subscripts.size() > 0) {
                ref.addProperty("name", baseDataName(id));
                ref.add("subscripts", subscripts);
                addCtxQualifiers(ref, id);
                return ref;
            }
            ref.addProperty("name", leafDataName(id));
            addCtxQualifiers(ref, id);
            return ref;
        }
        return litNode("");
    }

    /** A literal operand as a {@code lit} node, or a {@code figurative} one. */
    private static JsonElement serializeLiteralCtx(CobolParser.LiteralContext lit) {
        CobolParser.LiteralContext repeated = allRepeatedLiteral(lit);
        if (repeated != null) {
            return allLiteralNode(repeated);
        }
        if (lit != null && lit.figurativeConstant() != null) {
            String canonical = canonicalFigurativeCtx(lit.figurativeConstant());
            if (canonical != null) {
                JsonObject fig = new JsonObject();
                fig.addProperty("kind", "figurative");
                fig.addProperty("value", canonical);
                return fig;
            }
        }
        return litNode(lit != null ? lit.getText() : "", lit);
    }

    /**
     * Subscripts carried by a grammar-context identifier's {@code tableCall}, in
     * source order, each as a structured expression node — the ctx-side twin of
     * {@link #serializeSubscripts}.
     */
    private static JsonArray serializeIdentifierSubscripts(CobolParser.IdentifierContext id) {
        JsonArray arr = new JsonArray();
        if (id == null) {
            return arr;
        }
        CobolParser.TableCallContext tableCall = id.tableCall();
        if (tableCall != null) {
            for (CobolParser.SubscriptContext sub : tableCall.subscript()) {
                arr.add(serializeSubscriptCtx(sub));
            }
        }
        if (arr.size() == 0) {
            collectInTableSubscripts(id, arr);
        }
        return arr;
    }

    /** The subscript ALL of an intrinsic-function table argument. */
    private static boolean isAllSubscript(org.antlr.v4.runtime.ParserRuleContext ctx) {
        return ctx instanceof CobolParser.SubscriptContext
                && ((CobolParser.SubscriptContext) ctx).ALL() != null;
    }

    private static JsonObject allSubscriptNode() {
        JsonObject all = new JsonObject();
        all.addProperty("kind", "all");
        return all;
    }

    /** Grammar: subscript : ALL | arithmeticExpression | integerLiteral | qualifiedDataName | indexName */
    private static JsonElement serializeSubscriptCtx(CobolParser.SubscriptContext sub) {
        if (sub == null) {
            return litNode("");
        }
        if (isAllSubscript(sub)) {
            return allSubscriptNode();
        }
        if (sub.arithmeticExpression() != null) {
            return serializeArithExprCtx(sub.arithmeticExpression());
        }
        if (sub.qualifiedDataName() != null || sub.indexName() != null) {
            JsonObject ref = new JsonObject();
            ref.addProperty("kind", "ref");
            CobolParser.QualifiedDataNameFormat1Context f1 = findQualifiedDataNameFormat1(sub);
            ref.addProperty(
                    "name",
                    (f1 != null && f1.dataName() != null)
                            ? f1.dataName().getText()
                            : sub.getText());
            addCtxQualifiers(ref, sub);
            return ref;
        }
        return litNode(sub.getText());
    }

    /**
     * Maps a figurative-constant grammar context to the canonical comparison string.
     * Mirrors {@link #canonicalFigurative} but reads ANTLR terminal nodes directly,
     * for the grammar-context fallback path used on abbreviated conditions.
     */
    private static String canonicalFigurativeCtx(CobolParser.FigurativeConstantContext fc) {
        if (fc == null) return null;
        if (fc.SPACE() != null || fc.SPACES() != null) return "SPACES";
        if (fc.ZERO() != null || fc.ZEROS() != null || fc.ZEROES() != null) return "ZEROS";
        if (fc.LOW_VALUE() != null || fc.LOW_VALUES() != null) return "LOW-VALUES";
        if (fc.HIGH_VALUE() != null || fc.HIGH_VALUES() != null) return "HIGH-VALUES";
        if (fc.QUOTE() != null || fc.QUOTES() != null) return "QUOTES";
        return null;
    }

    static CobolParser.LiteralContext allRepeatedLiteral(CobolParser.LiteralContext lit) {
        if (lit == null || lit.figurativeConstant() == null || lit.figurativeConstant().ALL() == null) {
            return null;
        }
        return lit.figurativeConstant().literal();
    }

    private static JsonElement allLiteralNode(CobolParser.LiteralContext repeated) {
        if (repeated.figurativeConstant() != null) {
            return serializeLiteralCtx(repeated);
        }
        JsonObject fig = new JsonObject();
        fig.addProperty("kind", "figurative");
        fig.addProperty("value", "ALL");
        fig.addProperty("literal", repeated.getText());
        return fig;
    }

    private static JsonObject moveAllSource(CobolParser.LiteralContext literal) {
        JsonObject src = new JsonObject();
        src.addProperty("name", literal.getText());
        if (literal.figurativeConstant() == null) {
            src.addProperty("all", true);
        }
        return src;
    }

    private static JsonObject litNode(String value) {
        JsonObject lit = new JsonObject();
        lit.addProperty("kind", "lit");
        lit.addProperty("value", value);
        return lit;
    }

    /** A {@code lit} node, marked {@code "numeric"} when {@code ctx} is a numeric literal. */
    private static JsonObject litNode(String value, ParserRuleContext ctx) {
        JsonObject lit = litNode(value);
        if (isNumericLiteral(ctx)) {
            lit.addProperty("numeric", true);
        }
        return lit;
    }

    /** Marks an operand {@code "numeric"} when its value statement is a numeric literal. */
    private static void markNumeric(JsonObject operand, ValueStmt vs) {
        if (vs != null && isNumericLiteral(vs.getCtx())) {
            operand.addProperty("numeric", true);
        }
    }

    /**
     * True when {@code ctx} is, or wraps through single-child rules, the
     * grammar's numericLiteral: the lexer's NUMERICLITERAL, written as in the
     * source. The ASG reader applies DECIMAL-POINT IS COMMA to such literals.
     */
    static boolean isNumericLiteral(ParseTree ctx) {
        if (ctx instanceof CobolParser.NumericLiteralContext) {
            return true;
        }
        return ctx != null && ctx.getChildCount() == 1 && isNumericLiteral(ctx.getChild(0));
    }

    /**
     * Maps a ProLeap figurative-constant type to the canonical string the Python
     * condition lowering recognises. Returns {@code null} for figuratives without
     * a meaningful comparison fill (e.g. ALL/NULL) so callers fall back to text.
     */
    private static String canonicalFigurative(FigurativeConstant.FigurativeConstantType type) {
        if (type == null) return null;
        switch (type) {
            case SPACE:
            case SPACES:
                return "SPACES";
            case ZERO:
            case ZEROS:
            case ZEROES:
                return "ZEROS";
            case LOW_VALUE:
            case LOW_VALUES:
                return "LOW-VALUES";
            case HIGH_VALUE:
            case HIGH_VALUES:
                return "HIGH-VALUES";
            case QUOTE:
            case QUOTES:
                return "QUOTES";
            case NULL:
            case NULLS:
                return "NULL";
            default:
                return null;
        }
    }

    /**
     * Inserts spaces around comparison operators from ANTLR getText() output.
     */
    private static String insertSpaces(String text) {
        if (text == null) {
            return "";
        }
        return text
                .replaceAll("(?<=[A-Za-z0-9-])([><=])", " $1")
                .replaceAll("([><=])(?=[A-Za-z0-9-])", "$1 ");
    }
}
