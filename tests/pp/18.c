#define M_RETI_ARG27(x,y,z,aa, ...)    aa
#define M_RET_ARG27(...)        M_RETI_ARG27(__VA_ARGS__)
#define M_COMMA_P(...)          M_RET_ARG27(__VA_ARGS__, 1, 1, 0, useless)
#define M_EMPTYI_DETECT(...)    0, 1,
#define M_EMPTYI_P_C1(...)      M_COMMA_P(M_EMPTYI_DETECT __VA_ARGS__ () )
#define EX
#define empty(x)
#define fnlike(x) yeah x
/* 如果下面的宏以空实参（X183）调用，那么 fnlike 与
   '(' 之间的 'x' 不会妨碍识别这仍是一次
   函数式宏调用。  */
#define usefnlike(x) fnlike x (x)
X181 M_EMPTYI_P_C1()
X182 M_EMPTYI_P_C1(x)
X183 usefnlike()
