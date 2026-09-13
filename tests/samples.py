"""Realistic inputs shared by the algorithm tests."""

from __future__ import annotations

# The classic patience-diff example: `fib` is added above `frobnitz`, one
# line is dropped from `frobnitz`, and `fact` is removed. Myers matches the
# braces and `return 1;` of `fact` against those of `fib` and interleaves
# the two functions; unique-line anchoring keeps each function whole.
FROBNITZ_OLD = """\
#include <stdio.h>

// Frobs foo heartily
int frobnitz(int foo)
{
    int i;
    for(i = 0; i < 10; i++)
    {
        printf("Your answer is: ");
        printf("%d\\n", foo);
    }
}

int fact(int n)
{
    if(n > 1)
    {
        return fact(n-1) * n;
    }
    return 1;
}

int main(int argc, char **argv)
{
    frobnitz(fact(10));
}
""".splitlines()

FROBNITZ_NEW = """\
#include <stdio.h>

int fib(int n)
{
    if(n > 2)
    {
        return fib(n-1) + fib(n-2);
    }
    return 1;
}

// Frobs foo heartily
int frobnitz(int foo)
{
    int i;
    for(i = 0; i < 10; i++)
    {
        printf("%d\\n", foo);
    }
}

int main(int argc, char **argv)
{
    frobnitz(fib(10));
}
""".splitlines()
