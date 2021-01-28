#[macro_export]
// Return a u32 from a slice of bytes
macro_rules! u32_from_le_bytes {
    ( $( $x:expr ),* ) => {
        {
            $(
                u32::from_le_bytes($x.try_into().unwrap())
            ) *
        }
    };
}

#[macro_export]
// Return an i32 from a slice of bytes
macro_rules! i32_from_be_bytes {
    ( $( $x:expr ),* ) => {
        {
            $(
                i32::from_be_bytes($x.try_into().unwrap())
            ) *
        }
    };
}

#[macro_export]
// Return a [u8; 32] array from a slice of bytes
macro_rules! u8_32_from_bytes {
    ( $( $x:expr ),* ) => {
        {
            $(
                $x.try_into().unwrap()
            ) *
        }
    };
}
