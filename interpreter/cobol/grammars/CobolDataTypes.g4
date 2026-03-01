/*
* Copyright (C) 2024, Avishek Sen Gupta <avishek.sen.gupta@gmail.com>
* All rights reserved.
*
* This software may be modified and distributed under the terms
* of the MIT license. See the LICENSE file for details.
*/

parser grammar CobolDataTypes;
options {tokenVocab = CobolDataTypesLexer;}

startRule : dataTypeSpec EOF;

dataTypeSpec
   : fraction | alphanumeric | pointer
   ;

pointer : POINTER;

fraction
   : SIGN_SYMBOL? leadingScalingIndicator* (bothSidesOfDecimalPoint | onlyLeftOfDecimalPoint | onlyRightOfDecimalPoint | integer) trailingScalingIndicator*
   ;
alphanumeric
   : leftSideAlphanumericIndicator* alphaNumericIndicator rightSideAlphanumericIndicator*
   ;

leftSideAlphanumericIndicator: alphaNumericIndicator | digitIndicator;
rightSideAlphanumericIndicator: alphaNumericIndicator | digitIndicator;
onlyLeftOfDecimalPoint: integerPart decimalPointLocator;
onlyRightOfDecimalPoint: decimalPointLocator fractionalPart;
bothSidesOfDecimalPoint: integerPart decimalPointLocator fractionalPart;

integer: digitIndicator+;
integerPart: digitIndicator+;
fractionalPart: digitIndicator+;

alphaNumericIndicator: charTypeIndicator | nchars;
digitIndicator: numberTypeIndicator | ndigits;

ndigits: numberTypeIndicator numberOf;
nchars: charTypeIndicator numberOf;

numberOf: NUMBEROF;
decimalPointLocator: DECIMALPOINTLOCATOR;
leadingScalingIndicator: SCALINGINDICATOR;
trailingScalingIndicator: SCALINGINDICATOR;
numberTypeIndicator: CHAR_NINE | CHAR_Z;
charTypeIndicator: ALPHANUMERICINDICATOR;
