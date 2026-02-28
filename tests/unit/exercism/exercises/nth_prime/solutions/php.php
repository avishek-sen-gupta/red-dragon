<?php
function nthPrime($n) {
    $count = 0;
    $candidate = 2;
    while ($count < $n) {
        $isPrime = 1;
        $divisor = 2;
        while ($divisor * $divisor <= $candidate) {
            if ($candidate % $divisor == 0) {
                $isPrime = 0;
            }
            $divisor = $divisor + 1;
        }
        if ($isPrime == 1) {
            $count = $count + 1;
        }
        if ($count < $n) {
            $candidate = $candidate + 1;
        }
    }
    return $candidate;
}

$answer = nthPrime(1);
?>
