/*
 * Copyright (C) 2012  Floris Bos <bos@je-eigen-domein.nl>
 * Copyright (c) 2014  Luc Verhaegen <libv@skynet.be>
 * Copyright (c) 2016  Daniel Perron
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.

   Code took from 
   https://github.com/NextThingCo/sunxi-tools/blob/master/meminfo.c

   This Program  will write  the  INT_DEBOUNCING_REGISTER to  1 to set 24MHz interrupt
 */



#include <errno.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>


#define PIO_REG_SIZE 0x228 /*0x300*/

int main()
{

    int pagesize = sysconf(_SC_PAGESIZE);

    int addr = 0x01c20800 & ~(pagesize - 1);
    int offset = 0x01c20800 & (pagesize - 1);
    char * buff;
    unsigned int * PioRegister;

    int fd = open("/dev/mem",O_RDWR);
    if (fd == -1) {
        perror("open /dev/mem");
        exit(1);
    }
    buff = mmap(NULL, (0x800 + pagesize - 1) & ~(pagesize - 1), PROT_WRITE | PROT_READ, MAP_SHARED, fd, addr);
    PioRegister = (unsigned int *) &buff[offset + 0x218];

    if (!PioRegister) {
        perror("Can't remove INT debouncing!");
        exit(1);
    }
    close(fd);
    // ok set  int debounce regiter to 1 (32bits)
    *PioRegister = 1;
    return 0;
}

