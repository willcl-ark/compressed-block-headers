// use std::io::Read;
//
// #[macro_export]
// macro_rules! u8_from_le_bytes {
//     ($x:expr) => {
//         u8::from_le_bytes($x.try_into().unwrap())
//     };
// }
//
// #[macro_export]
// macro_rules! u32_from_le_bytes {
//     ($x:expr) => {
//         u32::from_le_bytes($x.try_into().unwrap())
//     };
// }
//
// #[macro_export]
// macro_rules! i32_from_be_bytes {
//     ($x:expr) => {
//         i32::from_be_bytes($x.try_into().unwrap())
//     };
// }
//
// #[macro_export]
macro_rules! read_le_u8 {
    ($reader:stmt) => {
        let mut buffer: [u8; 1] = [0; 1];
        $reader.read_exact(buffer);
        u8::from_le_bytes(buffer)
    };
}

#[macro_export]
macro_rules! read_le_i16 {
    ($reader:item) => {
        let buffer: [u8; 2] = [0; 2];
        reader.read_exact(buffer);
        i16::from_le_bytes(buffer.try_into().unwrap())
    };
}

#[macro_export]
macro_rules! read_le_u32 {
    ($reader:item) => {
        let buffer: [u8; 4] = [0; 4];
        reader.read_exact(buffer);
        u32::from_le_bytes(buffer.try_into().unwrap())
    };
}

#[macro_export]
macro_rules! read_be_i32 {
    ($reader:item) => {
        let buffer: [u8; 4] = [0; 4];
        reader.read_exact(buffer);
        i32::from_be_bytes(buffer.try_into().unwrap())
    };
}

#[macro_export]
macro_rules! read_32_bytes {
    ($reader:item) => {
        let buffer: [u8; 32] = [0; 32];
        reader.read_exact(buffer);
        buffer
    };
}
