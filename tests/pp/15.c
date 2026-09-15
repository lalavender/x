// 如果两个词法单元在回读时会合并成一个词法单元，
// 就在它们之间插入一个空格

#define n(x) x

return (n(long)n(double))d;
return n(A)n(++)n(+)n(B);
return n(A)n(+)n(++)n(B);
return n(A)n(++)n(+)n(+)n(B);

// 不是十六进制浮点数
return n(0x1E)n(-1);

// 与 gcc 不同，但正确
// XXX: return n(x)+n(x)-n(1)+n(1)-2;

// 与 gcc 不同，但不可能出现在合法的 C 中
// XXX: return n(x)n(x)n(1)n(2)n(x);
