#include<malloc.h>
int main(){
    void *p;
    while(1)
        p=malloc(1024*1024*100);
}