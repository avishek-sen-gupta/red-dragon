char* reverseString(char* s, int n) {
    char* result = "";
    int i = n - 1;
    while (i >= 0) {
        result = result + s[i];
        i = i - 1;
    }
    return result;
}

char* answer = reverseString("robot", 5);
