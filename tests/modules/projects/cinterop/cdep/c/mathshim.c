#include <math.h>
#include <stdint.h>
#include "value.h"

int32_t cdep_round(double value) {
    return (int32_t)lrint(value) + CDEP_BIAS;
}
