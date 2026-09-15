/* ---------------------------------------------- */
/* alloca86_64.S */

.globl __bound_alloca
__bound_alloca:

#ifdef _WIN32
    # 未实现边界检查
    pop     %rdx
    mov     %rcx,%rax
    add     $15,%rax
    and     $-16,%rax
    jz      p3

p1:
    cmp     $4096,%rax
    jbe     p2
    test    %rax,-4096(%rsp)
    sub     $4096,%rsp
    sub     $4096,%rax
    jmp p1
p2:

    sub     %rax,%rsp
    mov     %rsp,%rax
    add     $32,%rax

p3:
    push    %rdx
    ret
#else
    pop     %rdx
    mov     %rdi,%rax
    mov     %rax,%rsi	# size，即传给 __bound_new_region 的第二个参数

    add     $15,%rax
    and     $-16,%rax
    jz      p3


    sub     %rax,%rsp
    mov     %rsp,%rdi	# pointer，即传给 __bound_new_region 的第一个参数
    mov     %rsp,%rax

    push    %rdx
    push    %rax
    call   __bound_new_region
    pop     %rax
    pop     %rdx

p3:
    push    %rdx
    ret
#endif

/* ---------------------------------------------- */
