#ifndef _STDDEF_H
#define _STDDEF_H

typedef __SIZE_TYPE__ size_t;
typedef __PTRDIFF_TYPE__ ssize_t;
typedef __WCHAR_TYPE__ wchar_t;
typedef __PTRDIFF_TYPE__ ptrdiff_t;
typedef __PTRDIFF_TYPE__ intptr_t;
typedef __SIZE_TYPE__ uintptr_t;

#ifndef __int8_t_defined
#define __int8_t_defined
typedef signed char int8_t;
typedef signed short int int16_t;
typedef signed int int32_t;
#ifdef __LP64__
typedef signed long int int64_t;
#else
typedef signed long long int int64_t;
#endif
typedef unsigned char uint8_t;
typedef unsigned short int uint16_t;
typedef unsigned int uint32_t;
#ifdef __LP64__
typedef unsigned long int uint64_t;
#else
typedef unsigned long long int uint64_t;
#endif
#endif

#ifndef NULL
#define NULL ((void*)0)
#endif

#define offsetof(type, field) ((size_t)&((type *)0)->field)

void *alloca(size_t size);

#endif

/* 较老的 glibc 需要从 <stddef.h> 得到 wint_t（当通过
   __need_wint_t 请求时，否则 stddef.h 不允许
   定义该类型）。注意它必须位于常规的
   _STDDEF_H 卫哨之外，这样即使我们已经包含过该文件
   （当时并未要求 wint_t）它依然有效。其他一些库如果已经
   提供了该类型就定义 _WINT_T，因此我们可以用它作为卫哨。
   TCC 为我们定义了 __WINT_TYPE__。  */
#if defined (__need_wint_t)
#ifndef _WINT_T
#define _WINT_T
typedef __WINT_TYPE__ wint_t;
#endif
#undef __need_wint_t
#endif
